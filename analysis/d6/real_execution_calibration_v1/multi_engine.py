"""Multi-crypto coordinator — runs N concurrent opportunities across cryptos.

Each crypto/timeframe pair gets its own:
  - StreamBook (WebSocket order book)
  - Binance price feed
  - Signal evaluation
  - Opportunity pipeline

Shared:
  - Account (one wallet)
  - Capital allocation across markets
  - Risk management (global drawdown, total exposure)
  - Logging/journal
"""
import asyncio, copy, hashlib, os, time, uuid, shutil, traceback
from decimal import Decimal
from collections import deque
from pathlib import Path

from .core import dec, digest, encoded, redact
from .v1_binding import bind, verify
from .transport import validate_signed
from .incidents import capture as capture_incident
from .engine import HumanArm, Coordinator, transient_availability, TRANSIENT_AVAILABILITY


class MarketSlot:
    """Holds state for one crypto/timeframe trading slot."""
    
    def __init__(self, crypto, timeframe_label, timeframe_s,
                 condition_id, token_up, token_down, market_slug):
        self.crypto = crypto
        self.timeframe_label = timeframe_label
        self.timeframe_s = timeframe_s
        self.condition_id = condition_id
        self.token_up = token_up
        self.token_down = token_down
        self.market_slug = market_slug
        self.key = f"{crypto}_{timeframe_label}"
        
        # Runtime state
        self.coordinator = None
        self.stream_book = None
        self.binance_symbol = f"{crypto}USDT"
        self.active = True
        self.opportunities = 0
        self.last_trade_ms = 0
        self.pnl = Decimal("0")
        
    def __repr__(self):
        return f"<MarketSlot {self.key}>"


class MultiCoordinator:
    """Orchestrates N market slots with shared account and capital allocation."""
    
    def __init__(self, ledger, account_source, kill_path,
                 arm=None, clock=None, sleep=None):
        self.ledger = ledger
        self.account_source = account_source
        self.kill_path = Path(kill_path)
        self.arm = arm
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.sleep = sleep or asyncio.sleep
        
        self.slots = {}  # key -> MarketSlot
        self.sub_coordinators = {}  # key -> Coordinator
        
        # Capital allocation
        self.total_cash = Decimal("109.16")
        self.allocated = {}  # key -> Decimal allocated
        self.max_per_market = Decimal("25")
        self.max_total = Decimal("100")
        self.max_concurrent = 4
        
        # Global risk
        self.global_pnl = Decimal("0")
        self.max_drawdown = Decimal("-50")  # -$50 global stop
        self.consecutive_losses = 0
        self.max_consecutive_losses = 5
        
        # Price feeds
        self.binance_collectors = {}
        self.tick_windows = {}  # key -> deque
        
        self.busy_slots = set()  # keys currently in a trade
        self.stop = False
        
        self.runtime_counts = {
            'OPPORTUNITIES': 0,
            'SHADOW_REJECTIONS': 0,
            'MARKETS_ACTIVE': 0,
        }
        
    def add_slot(self, slot):
        """Register a market slot."""
        self.slots[slot.key] = slot
        self.allocated[slot.key] = Decimal("0")
        self.tick_windows[slot.key] = deque(maxlen=4096)
        self.runtime_counts['MARKETS_ACTIVE'] = len(self.slots)
        self.ledger.emit('MULTI_SLOT_ADDED', {
            'key': slot.key,
            'crypto': slot.crypto,
            'timeframe': slot.timeframe_label,
            'condition_id': slot.condition_id,
            'total_slots': len(self.slots),
        })
        
    def available_capital(self):
        """Return unallocated cash."""
        used = sum(self.allocated.values())
        return min(self.total_cash - used, self.max_total - used)
    
    def can_allocate(self, amount=Decimal("25")):
        """Check if we can allocate $amount to a new trade."""
        active_trades = sum(1 for v in self.allocated.values() if v > 0)
        if active_trades >= self.max_concurrent:
            return False
        return self.available_capital() >= amount
    
    def reserve(self, key, amount):
        """Reserve capital for a trade."""
        if not self.can_allocate(amount):
            return False
        self.allocated[key] += amount
        return True
    
    def release(self, key, amount=None):
        """Release reserved capital."""
        if amount is None:
            self.allocated[key] = Decimal("0")
        else:
            self.allocated[key] = max(Decimal("0"), self.allocated[key] - amount)
    
    def update_pnl(self, key, change):
        """Track PnL per market and globally."""
        self.slots[key].pnl += change
        self.global_pnl += change
        
        if change < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        self.ledger.emit('MULTI_PNL', {
            'key': key,
            'change': str(change),
            'market_pnl': str(self.slots[key].pnl),
            'global_pnl': str(self.global_pnl),
            'consecutive_losses': self.consecutive_losses,
        })
        
        # Global drawdown stop
        if self.global_pnl < self.max_drawdown:
            self.ledger.halt('MULTI_MAX_DRAWDOWN', {
                'global_pnl': str(self.global_pnl),
                'max_drawdown': str(self.max_drawdown),
            })
            self.stop = True
            
        # Consecutive losses stop
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.ledger.halt('MULTI_CONSECUTIVE_LOSSES', {
                'count': self.consecutive_losses,
                'max': self.max_consecutive_losses,
            })
            self.stop = True
    
    def guard(self, entry=True):
        """Global guard — checks arm, kill switch, disk."""
        verify()
        if entry and shutil.disk_usage(self.ledger.journal.path.parent).free < 512 * 1024 ** 2:
            self.ledger.halt('DISK_LOW')
        if self.arm is None:
            raise ValueError('CALIBRATION_NOT_ARMED')
        self.arm.check(self.ledger.journal.experiment_id, entry)
        if self.kill_path.exists() and not self.ledger.stop:
            self.ledger.halt('MANUAL_KILL')
        if entry and (self.ledger.stop or self.ledger.stop_new_entries):
            raise ValueError('STOP_NEW_ENTRIES')
        if self.stop:
            raise ValueError('MULTI_STOPPED')
    
    async def on_btc_tick(self, tick):
        """Handle BTC price tick (legacy, maps to BTC_5m slot)."""
        key = "BTC_5m"
        await self._on_tick(key, tick)
    
    async def on_eth_tick(self, tick):
        """Handle ETH price tick."""
        key = "ETH_5m"
        await self._on_tick(key, tick)
    
    async def on_sol_tick(self, tick):
        """Handle SOL price tick."""
        key = "SOL_5m"
        await self._on_tick(key, tick)
    
    async def _on_tick(self, key, tick):
        """Generic tick handler for any crypto."""
        if self.stop:
            return
        if tick.event_ts_ms is None or tick.recv_ts_ms is None:
            return
        
        window = self.tick_windows[key]
        window.append({
            'source_ms': tick.event_ts_ms,
            'receive_ms': tick.recv_ts_ms,
            'price': tick.price,
        })
        
        # Route to sub-coordinator if exists
        if key in self.sub_coordinators:
            try:
                await self.sub_coordinators[key].on_btc(tick)
            except BaseException:
                pass
    
    async def run(self):
        """Main loop — reconciles account and checks opportunities."""
        self.ledger.emit('MULTI_START', {
            'slots': list(self.slots.keys()),
            'total_cash': str(self.total_cash),
            'max_per_market': str(self.max_per_market),
            'max_concurrent': self.max_concurrent,
        })
        
        while not self.stop and not self.ledger.stop:
            try:
                self.guard(entry=False)
                
                # Reconcile account
                snapshot = await self.account_source.snapshot()
                cash = Decimal(str(snapshot.get('cash', '0')))
                self.total_cash = cash
                
                self.ledger.emit('MULTI_RECONCILE', {
                    'cash': str(cash),
                    'available': str(self.available_capital()),
                    'allocated': {k: str(v) for k, v in self.allocated.items()},
                    'global_pnl': str(self.global_pnl),
                    'active_slots': len(self.busy_slots),
                })
                
                await self.sleep(5)  # 5s reconciliation cycle
                
            except ValueError as exc:
                if transient_availability(exc):
                    self.ledger.emit('MULTI_TRANSIENT', {'error': str(exc)})
                    await self.sleep(2)
                    continue
                if str(exc) in ('STOP_NEW_ENTRIES', 'MULTI_STOPPED'):
                    break
                raise
            except BaseException:
                self.ledger.halt('MULTI_FATAL')
                raise
    
    def close(self):
        """Clean shutdown."""
        self.stop = True
        for key, sub in self.sub_coordinators.items():
            try:
                sub.ledger.close()
            except BaseException:
                pass
        self.ledger.emit('MULTI_STOP', {
            'global_pnl': str(self.global_pnl),
            'total_opportunities': self.runtime_counts['OPPORTUNITIES'],
        })
