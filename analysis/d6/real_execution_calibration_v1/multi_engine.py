"""Multi-crypto coordinator — runs N concurrent opportunities across cryptos.

Each crypto gets its own:
  - V1Strategy (price move detection)
  - Capital allocation
  - Opportunity pipeline

Shared:
  - Account (one wallet, one AsyncSecureClient)
  - Risk management (global drawdown, total exposure)
  - Logging/journal

Full trade pipeline: detect → shadow → reserve → sign → submit → fill → exit.
"""
import asyncio, copy, hashlib, time, uuid
from decimal import Decimal
from pathlib import Path

from .core import dec, digest, ZERO
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
        self.book_adapter = None
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
                 secure_client=None, sdk_port=None,
                 fee_ceiling_fn=None, arm=None, clock=None, sleep=None):
        self.ledger = ledger
        self.account_source = account_source
        self.kill_path = Path(kill_path)
        self.secure_client = secure_client
        self.sdk_port = sdk_port
        self.fee_ceiling_fn = fee_ceiling_fn
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

        self.busy_slots = set()
        self.stop = False

        # Snapshot rate-limiter: cache account snapshot for 2s
        self._last_snapshot_ts = 0.0
        self._cached_snapshot = None

        self.runtime_counts = {
            'OPPORTUNITIES': 0,
            'TRADES': 0,
            'FILLS': 0,
            'MARKETS_ACTIVE': 0,
        }

        self.measurements = {}  # client_id -> measurement dict

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
        """Full trade pipeline: shadow → reserve → sign → submit → exit."""
        if self.stop or self.ledger.stop:
            return
        if key in self.busy_slots:
            return

        slot = self.slots[key]
        self.busy_slots.add(key)
        op = f"{key}:{signal_ts}"

        try:
            self.runtime_counts['OPPORTUNITIES'] += 1
            slot.opportunities += 1
            print(f"MULTI: OPPORTUNITY {key} move={move:.3f}% side={side} ts={signal_ts}", flush=True)

            self.ledger.emit('MULTI_OPPORTUNITY', {
                'key': key, 'signal_ts': signal_ts, 'move_pct': move, 'side': side,
                'cash': str(self.total_cash), 'available': str(self.available_capital()),
                'opportunities': self.runtime_counts['OPPORTUNITIES'],
            })

            # 1. Guard & arm check
            self.guard()

            # 2. Determine which outcome token to buy
            #    BUY signal = price going up → buy UP token
            #    SELL signal = price going down → buy DOWN token
            buy_token = slot.token_up if side == "BUY" else slot.token_down
            condition_id = slot.condition_id
            market_slug = slot.market_slug

            # 3. Fetch order book
            if slot.book_adapter is None:
                print(f"MULTI: {key} no book adapter, skipping", flush=True)
                return

            try:
                book = await slot.book_adapter.snapshot(buy_token)
                if not book or not book.get('valid'):
                    print(f"MULTI: {key} invalid book, skipping", flush=True)
                    self.ledger.emit('OPPORTUNITY_SKIPPED', {
                        'key': key, 'signal_ts': signal_ts, 'reason': 'INVALID_BOOK',
                    })
                    return
            except Exception as exc:
                print(f"MULTI: {key} book unavailable: {type(exc).__name__}: {exc}, skipping", flush=True)
                self.ledger.emit('OPPORTUNITY_SKIPPED', {
                    'key': key, 'signal_ts': signal_ts, 'reason': f'BOOK_FAILED:{type(exc).__name__}:{exc}',
                })
                return

            # 4. Calculate entry (buy 25$ of the token)
            asks = [(dec(p), dec(q)) for p, q in book.get('asks', [])]
            if not asks:
                print(f"MULTI: {key} empty asks for token {buy_token}, skipping (side={side})", flush=True)
                self.ledger.emit('OPPORTUNITY_SKIPPED', {
                    'key': key, 'signal_ts': signal_ts, 'reason': f'EMPTY_ASKS_{side}',
                })
                return

            # Simple fill: take from asks until we fill ~25$
            # Use 24.90 to guarantee price * taker_amount >= maker_amount
            # after SDK floor-division of maker_amount/price. 24.99 fails because
            # floor(24.99/0.99)*0.99 = 24.98999976 < 24.99 (SIGNED_ENTRY_CAP_OR_PRICE).
            remaining = Decimal("0.40")  # fit within ~0.47 USDC remaining on-chain balance
            total_shares = ZERO
            total_cost = ZERO
            limit_price = None
            for p, q in asks:
                take = min(remaining / p, q)
                if take <= 0:
                    break
                total_shares += take
                cost = take * p
                total_cost += cost
                remaining -= cost
                limit_price = p
                if remaining <= Decimal("0.01"):
                    break

            if total_shares <= 0:
                print(f"MULTI: {key} no depth for entry, skipping", flush=True)
                return

            if self.fee_ceiling_fn:
                fee_risk = self.fee_ceiling_fn()
            else:
                fee_risk = None

            fee_ceiling = Decimal("0.50")  # 50c fee buffer

            # 5. Create shadow
            shadow = {
                'opportunity_id': op, 'market': condition_id, 'token': buy_token,
                'direction': side, 'signal_ts': signal_ts, 'btc_move': move,
                'expected_entry_price': str(limit_price),
                'expected_quantity': str(total_shares),
                'expected_entry_cost': str(total_cost),
                'expected_fill': str(total_shares),
                'expected_fee': str(fee_ceiling),
                'strategy_hashes': verify(),
            }
            self.ledger.seal_shadow(op, shadow)

            # 6. Reconcile account before entry (rate-limited to 2s, non-fatal on failure)
            now = self.clock()
            if now - self._last_snapshot_ts >= 2.0:
                try:
                    snapshot = await asyncio.wait_for(
                        self.account_source.snapshot(), timeout=15
                    )
                    self._cached_snapshot = snapshot
                    self._last_snapshot_ts = now
                except Exception as exc:
                    print(f"MULTI: {key} snapshot failed ({exc}), using cached cash={self.total_cash}", flush=True)
                    # Non-fatal: use last known cash (safe since no trades active)
                    snapshot = self._cached_snapshot or {'cash': str(self.total_cash)}
            else:
                snapshot = self._cached_snapshot or {'cash': str(self.total_cash)}

            self.total_cash = Decimal(str(snapshot.get('cash', '0')))

            # 7. Reserve capital
            amount = min(Decimal("24.90"), total_cost).quantize(Decimal('.01'), rounding='ROUND_DOWN')
            try:
                self.ledger.reserve(op, amount, fee_ceiling, fee_risk=fee_risk, token=buy_token)
            except ValueError as exc:
                print(f"MULTI: {key} reserve failed: {exc}", flush=True)
                self.ledger.emit('OPPORTUNITY_SKIPPED', {
                    'key': key, 'signal_ts': signal_ts, 'reason': f'RESERVE_FAILED:{exc}',
                })
                return

            self.allocated[key] += amount + fee_ceiling
            slot.trades += 1
            slot.last_trade_ms = self.clock()

            # 8. Sign and submit order via SDKPort
            client_id = f"{op}:entry"
            self.ledger.intent(client_id, 'BUY', buy_token, condition_id,
                               limit_price, total_shares, amount, book, self.clock())

            if self.sdk_port is None:
                print(f"MULTI: {key} no SDK port configured, shadow sealed but no order sent", flush=True)
                self.ledger.emit('OPPORTUNITY_COMPLETE', {'opportunity_id': op, 'key': key, 'simulated': True})
                return

            signed = await self.sdk_port.prepare(
                token=buy_token, side='BUY',
                amount=str(amount), price=str(limit_price),
                shares=str(total_shares),
            )

            self.ledger.emit('SEND_DISPATCH_INTENT', {
                'client_id': client_id, 'local_send_call_ms': self.clock(),
                'socket_send_proven': False,
            })

            # 9. Submit the order
            response = await self.sdk_port.submit_once(client_id, signed)
            reply_ms = self.clock()
            self.measurements[client_id] = {
                'client_id': client_id, 'send_call_ms': self.clock(),
                'response_ms': reply_ms, 'ack_latency_ms': reply_ms - self.clock(),
            }

            if not self.ledger.ack(client_id, response, reply_ms):
                print(f"MULTI: {key} ACK failed", flush=True)
                return

            # 10. Get fills
            try:
                evidence = await asyncio.wait_for(
                    self.account_source.execution(response['order_id']), timeout=10
                )
                for fill in evidence['fills']:
                    if not self.ledger.fill(client_id, fill):
                        print(f"MULTI: {key} fill qualification failed", flush=True)
                        return
                if not self.ledger.terminal(client_id, evidence['terminal_status'],
                                             evidence['cumulative_shares']):
                    print(f"MULTI: {key} terminal qualification failed", flush=True)
                    return
            except (KeyError, ValueError, asyncio.TimeoutError) as exc:
                print(f"MULTI: {key} fill observation failed: {exc}, discarding opportunity", flush=True)
                self.ledger.discard_opportunity(op)
                self.release(key)
                return

            self.runtime_counts['TRADES'] += 1
            self.runtime_counts['FILLS'] += len(evidence.get('fills', []))
            print(f"MULTI: {key} ENTRY FILLED — {evidence.get('cumulative_shares', '?')} shares @ {limit_price}", flush=True)

            # 11. Hold 500ms then exit
            held = self.ledger.positions.get(buy_token, ZERO)
            if held > 0:
                await self.sleep(0.5)

                # Fetch exit book
                exit_book = await slot.book_adapter.snapshot(buy_token)
                if not exit_book or not exit_book.get('valid'):
                    print(f"MULTI: {key} exit book invalid, holding position", flush=True)
                    self.ledger.emit('OPPORTUNITY_COMPLETE', {
                        'opportunity_id': op, 'key': key, 'exit_skipped': 'INVALID_BOOK',
                    })
                    return

                # Sell on bids
                bids = [(dec(p), dec(q)) for p, q in exit_book.get('bids', [])]
                if not bids:
                    print(f"MULTI: {key} no bids for exit, holding position", flush=True)
                    return

                sell_shares = held
                remaining_sell = sell_shares
                exit_price = None
                for p, q in bids:
                    take = min(remaining_sell, q)
                    if take <= 0:
                        break
                    remaining_sell -= take
                    exit_price = p
                    if remaining_sell <= 0:
                        break

                if exit_price is None or sell_shares <= 0:
                    print(f"MULTI: {key} no exit depth, holding", flush=True)
                    return

                # Sign and submit SELL
                exit_client_id = f"{op}:exit"
                self.ledger.intent(exit_client_id, 'SELL', buy_token, condition_id,
                                   exit_price, sell_shares, Decimal("0"), exit_book, self.clock())

                exit_signed = await self.sdk_port.prepare(
                    token=buy_token, side='SELL',
                    amount='0', price=str(exit_price),
                    shares=str(sell_shares),
                )
                exit_response = await self.sdk_port.submit_once(exit_client_id, exit_signed)

                if not self.ledger.ack(exit_client_id, exit_response, self.clock()):
                    print(f"MULTI: {key} exit ACK failed", flush=True)
                    return

                try:
                    exit_evidence = await asyncio.wait_for(
                        self.account_source.execution(exit_response['order_id']), timeout=10
                    )
                    for fill in exit_evidence['fills']:
                        if not self.ledger.fill(exit_client_id, fill):
                            print(f"MULTI: {key} exit fill qualification failed", flush=True)
                            return
                    if not self.ledger.terminal(exit_client_id, exit_evidence['terminal_status'],
                                                 exit_evidence['cumulative_shares']):
                        print(f"MULTI: {key} exit terminal failed", flush=True)
                        return
                except (KeyError, ValueError, asyncio.TimeoutError) as exc:
                    print(f"MULTI: {key} exit fill observation failed: {exc}", flush=True)
                    return

                # Track PnL
                entry_cost = self.ledger.trades[op]['spent']
                exit_proceeds = self.ledger.trades[op]['proceeds']
                pnl_change = exit_proceeds - entry_cost - self.ledger.trades[op]['cash_fees']
                self.update_pnl(key, pnl_change)
                print(f"MULTI: {key} EXIT COMPLETE — PnL={pnl_change}", flush=True)

            # Release capital
            self.release(key)
            self.ledger.emit('OPPORTUNITY_COMPLETE', {'opportunity_id': op, 'key': key})

        except Exception as exc:
            if str(exc) in ('STOP_NEW_ENTRIES', 'MULTI_STOPPED'):
                return
            print(f"MULTI: {key} opportunity error: {type(exc).__name__}: {exc}", flush=True)
            self.ledger.emit('MULTI_TRANSIENT', {
                'key': key, 'error': str(exc), 'opportunity': op,
            })
            self.ledger.discard_opportunity(op)
            self.release(key)
            return
        finally:
            self.busy_slots.discard(key)

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
            'key': key, 'change': str(change),
            'market_pnl': str(self.slots[key].pnl),
            'global_pnl': str(self.global_pnl),
            'consecutive_losses': self.consecutive_losses,
        })

        if self.global_pnl < self.max_drawdown:
            self.ledger.halt('MULTI_MAX_DRAWDOWN', {
                'global_pnl': str(self.global_pnl),
                'max_drawdown': str(self.max_drawdown),
            })
            self.stop = True

        if self.consecutive_losses >= self.max_consecutive_losses:
            self.ledger.halt('MULTI_CONSECUTIVE_LOSSES', {
                'count': self.consecutive_losses,
                'max': self.max_consecutive_losses,
            })
            self.stop = True

    def guard(self, entry=True):
        """Global guard."""
        verify()
        if entry and self.kill_path.exists() and not self.ledger.stop:
            self.ledger.halt('MANUAL_KILL')
        if self.arm is None:
            raise ValueError('CALIBRATION_NOT_ARMED')
        self.arm.check(self.ledger.journal.experiment_id, entry)
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
                    'trades': self.runtime_counts['TRADES'],
                    'fills': self.runtime_counts['FILLS'],
                    'diagnostics': diagnostics,
                })
                print(f"MULTI: Cycle {cycle} — done, sleeping 10s", flush=True)

                await self.sleep(10)

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
            'total_trades': self.runtime_counts['TRADES'],
        })
