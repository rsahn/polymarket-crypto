"""Multi-crypto coordinator — runs N concurrent opportunities across cryptos.

Each crypto gets its own:
  - V1Strategy (price move detection)
  - Capital allocation
  - Opportunity pipeline

Shared:
  - Account (one wallet, one AsyncSecureClient)
  - Risk management (global drawdown, total exposure)
  - Logging/journal
"""
import asyncio, time
from decimal import Decimal
from pathlib import Path

from .core import dec, digest
from .v1_binding import verify
from .multi_v1_strategy import V1Strategy


class MarketSlot:
    """Holds state for one crypto trading slot."""
    
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
        self.binance_symbol = f"{crypto}USDT"
        self.stream_book = None
        self.strategy = None
        self.active = True
        self.opportunities = 0
        self.trades = 0
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
        
        # Capital allocation
        self.total_cash = Decimal("109.16")
        self.allocated = {}  # key -> Decimal
        self.max_per_market = Decimal("25")
        self.max_total = Decimal("100")
        self.max_concurrent = 4
        
        # Global risk
        self.global_pnl = Decimal("0")
        self.max_drawdown = Decimal("-50")
        self.consecutive_losses = 0
        self.max_consecutive_losses = 5
        
        # Binance collectors
        self.collectors = {}
        self.collector_tasks = {}
        
        self.busy_slots = set()
        self.stop = False
        
        self.runtime_counts = {
            'OPPORTUNITIES': 0,
            'TRADES': 0,
            'MARKETS_ACTIVE': 0,
        }
        
    def add_slot(self, slot):
        """Register a market slot with its V1 strategy."""
        self.slots[slot.key] = slot
        self.allocated[slot.key] = Decimal("0")
        
        # Create V1 strategy for this slot
        slot.strategy = V1Strategy(
            slot.binance_symbol,
            on_opportunity=lambda ts, move, side, k=slot.key: 
                self._on_opportunity(k, ts, move, side)
        )
        
        self.runtime_counts['MARKETS_ACTIVE'] = len(self.slots)
        self.ledger.emit('MULTI_SLOT_ADDED', {
            'key': slot.key,
            'crypto': slot.crypto,
            'timeframe': slot.timeframe_label,
            'condition_id': slot.condition_id,
            'total_slots': len(self.slots),
        })
        
    async def _on_opportunity(self, key, signal_ts, move, side):
        """Handle a V1 signal for a specific slot."""
        if self.stop or self.ledger.stop:
            return
        if key in self.busy_slots:
            return  # Already in a trade on this slot
        
        self.runtime_counts['OPPORTUNITIES'] += 1
        self.slots[key].opportunities += 1
        
        self.ledger.emit('MULTI_OPPORTUNITY', {
            'key': key,
            'signal_ts': signal_ts,
            'move_pct': move,
            'side': side,
            'cash': str(self.total_cash),
            'available': str(self.available_capital()),
            'opportunities': self.runtime_counts['OPPORTUNITIES'],
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
        """Global guard."""
        verify()
        if entry and Path(self.kill_path).exists() and not self.ledger.stop:
            self.ledger.halt('MANUAL_KILL')
        if entry and (self.ledger.stop or self.ledger.stop_new_entries):
            raise ValueError('STOP_NEW_ENTRIES')
        if self.stop:
            raise ValueError('MULTI_STOPPED')
    
    async def on_tick(self, key, tick):
        """Route a Binance tick to the right strategy."""
        if key not in self.slots:
            return
        slot = self.slots[key]
        if slot.strategy:
            await slot.strategy.on_tick(tick)
    
    async def run(self):
        """Main loop."""
        print("MULTI: Starting main reconciliation loop", flush=True)
        self.ledger.emit('MULTI_START', {
            'slots': list(self.slots.keys()),
            'total_cash': str(self.total_cash),
            'max_per_market': str(self.max_per_market),
            'max_concurrent': self.max_concurrent,
        })
        
        cycle = 0
        while not self.stop and not self.ledger.stop:
            try:
                self.guard(entry=False)
                cycle += 1
                
                # Reconcile account with timeout
                print(f"MULTI: Cycle {cycle} — snapshot...", flush=True)
                try:
                    snapshot = await asyncio.wait_for(
                        self.account_source.snapshot(), timeout=20
                    )
                    cash = Decimal(str(snapshot.get('cash', '0')))
                    self.total_cash = cash
                    print(f"MULTI: Cycle {cycle} — cash={cash}", flush=True)
                except asyncio.TimeoutError:
                    print(f"MULTI: Cycle {cycle} — snapshot TIMEOUT, retrying", flush=True)
                    self.ledger.emit('MULTI_TRANSIENT', {'error': 'SNAPSHOT_TIMEOUT'})
                    await self.sleep(5)
                    continue
                except ValueError as exc:
                    print(f"MULTI: Cycle {cycle} — snapshot error: {exc}", flush=True)
                    self.ledger.emit('MULTI_TRANSIENT', {'error': str(exc)})
                    await self.sleep(5)
                    continue
                
                # Collect diagnostics from all strategies
                diagnostics = {}
                for key, slot in self.slots.items():
                    if slot.strategy:
                        diagnostics[key] = slot.strategy.diagnostics()
                
                self.ledger.emit('MULTI_RECONCILE', {
                    'cash': str(cash),
                    'available': str(self.available_capital()),
                    'allocated': {k: str(v) for k, v in self.allocated.items()},
                    'global_pnl': str(self.global_pnl),
                    'active_slots': len(self.busy_slots),
                    'opportunities': self.runtime_counts['OPPORTUNITIES'],
                    'diagnostics': diagnostics,
                })
                print(f"MULTI: Cycle {cycle} — done, sleeping 10s", flush=True)
                
                await self.sleep(10)  # 10s reconciliation cycle
                
            except ValueError as exc:
                if str(exc) in ('STOP_NEW_ENTRIES', 'MULTI_STOPPED'):
                    break
                self.ledger.emit('MULTI_TRANSIENT', {'error': str(exc)})
                await self.sleep(2)
                continue
            except BaseException:
                self.ledger.halt('MULTI_FATAL')
                raise
    
    def close(self):
        """Clean shutdown."""
        self.stop = True
        self.ledger.emit('MULTI_STOP', {
            'global_pnl': str(self.global_pnl),
            'total_opportunities': self.runtime_counts['OPPORTUNITIES'],
        })
