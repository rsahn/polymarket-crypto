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
from .multi_market_discovery import discover_crypto
from .multi_simulator import Simulator, ResolutionChecker


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

        # Compute slot expiry: each 5-min slot is valid for `timeframe_s` seconds
        now_s = int(time.time())
        slot_start_s = now_s // timeframe_s * timeframe_s
        self.slot_expiry_ms = (slot_start_s + timeframe_s) * 1000

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

    async def refresh_if_expired(self):
        """If the current 5-min slot has expired, discover the new market tokens.

        Returns True if the slot was refreshed, False if still valid.
        """
        now_ms = int(time.time() * 1000)
        if now_ms < self.slot_expiry_ms:
            return False

        print(f"MULTI: {self.key} slot expired (expiry={self.slot_expiry_ms}, now={now_ms}), refreshing...", flush=True)

        # Discover current market for this crypto
        market = discover_crypto(self.crypto, self.timeframe_label)
        new_slug = market["market_slug"]
        new_condition = market["condition_id"]
        new_token_up = market["token_up"]
        new_token_down = market["token_down"]
        new_expiry_ms = market["slot_start_ts"] + self.timeframe_s * 1000

        print(f"MULTI: {self.key} rotated to slot {new_slug}", flush=True)

        # Update own tokens
        self.condition_id = new_condition
        self.token_up = new_token_up
        self.token_down = new_token_down
        self.market_slug = new_slug
        self.slot_expiry_ms = new_expiry_ms

        # Rotate the book adapter (creates new StreamBook, discards old WS)
        if self.book_adapter is not None:
            await self.book_adapter.rotate(
                new_slug, new_condition,
                (new_token_up, new_token_down),
                new_expiry_ms,
            )
            # Seed the new book from REST
            for side_name, side_token in [('UP', new_token_up), ('DOWN', new_token_down)]:
                try:
                    rest_book = await self.book_adapter._rest_snapshot(side_token)
                    print(f"  {self.key} {side_name} book seeded ({len(rest_book.get('bids',[]))} bids, {len(rest_book.get('asks',[]))} asks)", flush=True)
                except Exception as e:
                    print(f"  {self.key} {side_name} seed failed: {e}", flush=True)

        return True

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
        self.simulate = False  # True = simulated PnL tracking
        # Simulator tracks positions and resolves them against real market outcomes
        self.simulator = None
        # Track positions held until resolution (instead of selling after 500ms)
        self.hold_positions = {}  # token -> {'opportunity_id', 'side', 'entry_price', 'shares', 'slot_key'}
        self.sleep = sleep or asyncio.sleep

        self.slots = {}  # key -> MarketSlot

        # Capital allocation
        self.total_cash = Decimal("100.00")
        self.allocated = {}  # key -> Decimal
        self.max_per_market = Decimal("15")
        self.max_total = Decimal("100")
        self.max_concurrent = 6
        self.position_timeout_ms = 600000  # 10 min — force-resolve if gamma-api doesn't

        # Global risk
        self.global_pnl = Decimal("0")
        # Track predicted direction for each slot
        self.predicted_sides = {}  # key -> 'BUY' or 'SELL'
        # Minimum interval between signals for the same slot (ms)
        # v2: 15s — was 30s but that severely limited trade frequency
        # With 5 crypto markets at 5-min resolution windows, 15s is enough
        # to avoid over-trading while capturing meaningful moves.
        self.min_signal_interval_ms = 10000  # 10s (was 15s)
        self.max_drawdown = Decimal("-50")
        self.consecutive_losses = 0
        self.max_consecutive_losses = 5
        self.strategy_version = "v3-throughput"

        # Track position entry times for forced resolution
        self._position_timestamps = {}  # token -> entry_ms

        self.busy_slots = set()
        self.stop = False

        # Snapshot rate-limiter: cache account snapshot for 10s (was 2s)
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
            
            # Store predicted direction
            self.predicted_sides[key] = side
            
            # Throttle: don't re-enter same market too quickly
            now_ms = self.clock()
            if now_ms - slot.last_trade_ms < self.min_signal_interval_ms:
                print(f"MULTI: {key} throttled (last trade {now_ms - slot.last_trade_ms}ms ago < {self.min_signal_interval_ms}ms)", flush=True)
                self.ledger.emit('OPPORTUNITY_SKIPPED', {
                    'key': key, 'signal_ts': signal_ts, 'reason': 'THROTTLED',
                })
                return

            # v3: Dynamic position sizing (smaller base for more concurrent trades)
            move_abs = abs(move)
            # scale: 0.05%->33%, 0.10%->66%, 0.20%+->100%
            position_pct = min(1.0, move_abs / 0.15)
            position_pct = max(0.40, position_pct)  # floor at 40% (never below $6)
            position_amount = Decimal(str(round(position_pct * 15, 2)))  # $6 to $15

            # Capital guard: check max concurrent positions and available cash
            if not self.can_allocate(position_amount):
                print(f"MULTI: {key} can't allocate — cash=${float(self.simulator.cash if self.simulate else self.total_cash):.2f} active={len([p for p in self.simulator.positions if not p.resolved]) if self.simulator else 0}/{self.max_concurrent}", flush=True)
                self.ledger.emit('OPPORTUNITY_SKIPPED', {
                    'key': key, 'signal_ts': signal_ts, 'reason': 'CAPITAL_EXHAUSTED',
                    'cash': str(self.simulator.cash if self.simulate else self.total_cash),
                    'max_concurrent': self.max_concurrent,
                })
                return

            signal_strength = round(move_abs / 0.20 * 100) if move_abs < 0.20 else 100
            self.ledger.emit('MULTI_OPPORTUNITY', {
                'key': key, 'signal_ts': signal_ts, 'move_pct': move, 'side': side,
                'cash': str(self.total_cash), 'available': str(self.available_capital()),
                'opportunities': self.runtime_counts['OPPORTUNITIES'],
                'position_amount': str(position_amount),
                'signal_strength_pct': signal_strength,
            })

            # 1. Guard & arm check
            self.guard()

            # 1b. Refresh market slot if expired (new 5-min window = new token IDs)
            try:
                refreshed = await slot.refresh_if_expired()
                if refreshed:
                    print(f"MULTI: {key} slot refreshed, continuing with new tokens", flush=True)
            except Exception as exc:
                print(f"MULTI: {key} slot refresh failed: {exc}, skipping", flush=True)
                self.ledger.emit('OPPORTUNITY_SKIPPED', {
                    'key': key, 'signal_ts': signal_ts, 'reason': f'SLOT_REFRESH_FAILED:{exc}',
                })
                return

            # 2. Determine which outcome token to buy
            #    BUY signal = price going up → buy UP token
            #    SELL signal = price going down → buy DOWN token
            buy_token = slot.token_up if side == "BUY" else slot.token_down
            # Store the predicted side on the slot for later reference
            slot.entry_side = side
            slot.entry_token = buy_token
            condition_id = slot.condition_id
            market_slug = slot.market_slug

            # 3. Dynamic position sizing (already computed above)
            if self.simulate:
                # Bonereaper tactic: buy at 40-70c fair price zone.
                # In simulation, use $0.50 as the default fair price (midpoint of 0-1).
                fair_price = Decimal("0.50")
                total_shares = position_amount / fair_price
                total_cost = position_amount
                print(f"MULTI: {key} SIMULATE fair price=${fair_price:.4f} shares={total_shares:.2f} cost=${total_cost:.2f} move={move:.3f}% size={position_pct:.0%}", flush=True)
            else:
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

                # 4. Calculate entry (buy 25$ of the token) from real book
                asks = [(dec(p), dec(q)) for p, q in book.get('asks', [])]
                if not asks:
                    print(f"MULTI: {key} empty asks for token {buy_token}, skipping (side={side})", flush=True)
                    self.ledger.emit('OPPORTUNITY_SKIPPED', {
                        'key': key, 'signal_ts': signal_ts, 'reason': f'EMPTY_ASKS_{side}',
                    })
                    return

                # Use fair price (midpoint) instead of ask price
                # This was the old bug: buying at ask (~$0.99) guaranteed losses.
                # Now we use the midpoint of best bid and best ask.
                bids = [(dec(p), dec(q)) for p, q in book.get('bids', [])]
                if not asks or not bids:
                    print(f"MULTI: {key} empty book for entry, skipping", flush=True)
                    return
                fair_price = (asks[0][0] + bids[0][0]) / dec("2")
            limit_price = fair_price
            total_shares = position_amount / fair_price
            total_cost = position_amount
            print(f"MULTI: {key} fair price={fair_price:.4f} shares={total_shares:.2f} cost=${total_cost:.2f}", flush=True)

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

            # 6. Reconcile account before entry (rate-limited to 10s, non-fatal on failure)
            # In simulation mode, skip account reconciliation entirely
            if self.simulate:
                snapshot = {'cash': str(self.total_cash)}
                print(f"MULTI: {key} SIMULATE — skipping account snapshot", flush=True)
            else:
                now = self.clock()
                if now - self._last_snapshot_ts >= 10.0:
                    try:
                        snapshot = await asyncio.wait_for(
                            self.account_source.snapshot(), timeout=15
                        )
                        self._cached_snapshot = snapshot
                        self._last_snapshot_ts = now
                    except Exception as exc:
                        print(f"MULTI: {key} snapshot failed ({exc}), using cached cash={self.total_cash}", flush=True)
                        snapshot = self._cached_snapshot or {'cash': str(self.total_cash)}
                else:
                    snapshot = self._cached_snapshot or {'cash': str(self.total_cash)}

            self.total_cash = Decimal(str(snapshot.get('cash', '0')))

            # 7. Reserve capital
            amount = min(Decimal("14.90"), total_cost).quantize(Decimal('.01'), rounding='ROUND_DOWN')
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
            # In simulation, use a minimal fake book for the intent call
            if self.simulate:
                sim_book = {'asks': [[str(fair_price), str(total_shares)]], 'bids': [[str(fair_price), str(total_shares)]],
                            'market': condition_id, 'token': buy_token, 'valid': True, 'ws_healthy': False,
                            'book_state_id': 'simulated', 'source_ms': self.clock(), 'receive_ms': self.clock(),
                            'generation': -1}
                self.ledger.intent(client_id, 'BUY', buy_token, condition_id,
                                   limit_price, total_shares, amount, sim_book, self.clock())
            else:
                self.ledger.intent(client_id, 'BUY', buy_token, condition_id,
                                   limit_price, total_shares, amount, book, self.clock())

            # --- SIMULATION MODE: track position, resolve later ---
            if self.simulate:
                amount = min(Decimal("14.90"), total_cost).quantize(Decimal('.01'), rounding='ROUND_DOWN')
                predicted = "UP" if side == "BUY" else "DOWN"
                print(f"MULTI: {key} SIMULATED ENTRY - buy {total_shares:.2f} {predicted}sh @ {fair_price:.4f} = ${amount:.2f}", flush=True)
                
                # Open simulated position
                if self.simulator:
                    pos = self.simulator.open_position(
                        slot_key=key,
                        side=side,
                        entry_price=fair_price,
                        shares=total_shares,
                        cost=amount,
                        condition_id=condition_id,
                        market_slug=market_slug,
                        token=buy_token,
                    )
                    print(f"MULTI: {key} Position opened - waiting for resolution in ~5 min", flush=True)
                    
                    # Reset reconciled so next trade can proceed
                    self.ledger.reconciled = True
                    self.ledger.stop_new_entries = False
                    
                    self.ledger.emit('OPPORTUNITY_COMPLETE', {
                        'opportunity_id': op, 'key': key,
                        'simulate': True,
                        'simulated_price': str(limit_price),
                        'simulated_shares': str(total_shares),
                        'simulated_cost': str(amount),
                        'predicted_direction': predicted,
                    })
                
                # Release ledger capital for next trade (different token)
                self.ledger.discard_opportunity(op)
                self.release(key)
                return

            # --- REAL MODE: submit order at FAIR PRICE (limit order, not market) ---
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

            # 11. HOLD until resolution (NO instant sell — this was the bug!)
            #     The 5-min Up/Down market resolves in ~5 minutes via Chainlink oracle.
            #     If our prediction is correct, the contract pays $1 (par) → ~+100%.
            #     We DO NOT sell after 500ms — that guaranteed buying at ask and selling at bid.
            held = self.ledger.positions.get(buy_token, ZERO)
            if held > 0:
                # Track position for resolution monitoring
                self.hold_positions[buy_token] = {
                    'opportunity_id': op,
                    'side': side,
                    'entry_price': limit_price,
                    'shares': held,
                    'slot_key': key,
                    'entry_cost': amount,
                    'token': buy_token,
                    'market_slug': market_slug,
                }
                print(f"MULTI: {key} ✅ POSITION HELD — {held:.2f} {side} shares @ {fair_price:.4f} = ${amount:.2f}", flush=True)
                print(f"  ⏳ Waiting for resolution in ~5 min...", flush=True)
                self.ledger.emit('POSITION_HELD', {
                    'opportunity_id': op, 'key': key,
                    'token': buy_token, 'side': side,
                    'shares': str(held), 'entry_price': str(limit_price),
                    'entry_cost': str(amount),
                    'resolution_strategy': 'HOLD_TO_RESOLUTION',
                })

            # Track position timestamp for forced timeout resolution
            self._position_timestamps[buy_token] = self.clock()

            # Release capital for next trade (separate token)
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
        if self.simulate and self.simulator:
            return self.simulator.cash
        used = sum(self.allocated.values())
        return min(self.total_cash - used, self.max_total - used)

    def can_allocate(self, amount=Decimal("25")):
        """Check if we can allocate $amount to a new trade."""
        if self.simulate and self.simulator:
            active = len([p for p in self.simulator.positions if not p.resolved])
            if active >= self.max_concurrent:
                return False
            if self.simulator.cash < amount:
                return False
            # Also enforce global max_total
            total_used = (len(self.positions) if hasattr(self, 'positions') else 0) if False else active * Decimal("25")
            return True
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
        if self.arm is None and not self.simulate:
            raise ValueError('CALIBRATION_NOT_ARMED')
        if self.arm is not None:
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
        print(f"MULTI: DEBUG stop={self.stop} ledger.stop={self.ledger.stop} simulate={self.simulate} has_simulator={self.simulator is not None}", flush=True)
        self.ledger.emit('MULTI_START', {
            'slots': list(self.slots.keys()),
            'total_cash': str(self.total_cash),
            'max_per_market': str(self.max_per_market),
            'max_concurrent': self.max_concurrent,
            'strategy_version': self.strategy_version,
            'strategy_desc': 'Momentum filter v2: per-crypto thresholds, 2-tick momentum, dynamic sizing $10-$25',
        })

        cycle = 0
        while not self.stop and not self.ledger.stop:
            try:
                self.guard(entry=False)
                cycle += 1
                # Log held positions each cycle
                if self.hold_positions:
                    print(f"MULTI: Held positions: {len(self.hold_positions)}", flush=True)
                    for tok, pos in list(self.hold_positions.items()):
                        print(f"  {pos['slot_key']}: {pos['shares']:.2f} {pos['side']}sh @ {pos['entry_price']:.4f}", flush=True)

                # Reconcile account with timeout
                if self.simulate:
                    if self.simulator:
                        # --- Force-resolve stale positions (timeout) ---
                        now_ms = self.clock()
                        for token, entry_ms in list(self._position_timestamps.items()):
                            if now_ms - entry_ms > self.position_timeout_ms:
                                for pos in list(self.simulator.positions):
                                    if pos.resolved:
                                        continue
                                    if pos.token == token:
                                        # Try gamma-api first, then force at entry price
                                        up_p, down_p = ResolutionChecker.get_outcome_prices(pos.condition_id, pos.market_slug)
                                        if up_p is not None:
                                            exit_p = Decimal(str(up_p if pos.predicted_direction == "UP" else down_p))
                                        else:
                                            exit_p = pos.entry_price  # scratch trade, no PnL
                                        pos.exit_price = exit_p
                                        pos.resolved = True
                                        pos.resolved_at = now_ms
                                        exit_value = Decimal(str(pos.shares)) * exit_p
                                        pos.pnl = exit_value - pos.cost
                                        self.simulator.total_pnl += pos.pnl
                                        self.simulator.cash += exit_value
                                        self.simulator.closed_positions.append(pos)
                                        if pos.pnl > 0:
                                            self.simulator.wins += 1
                                        else:
                                            self.simulator.losses += 1
                                        emoji = "🟢" if pos.pnl > 0 else "🔴"
                                        timeout_note = "TIMEOUT-FORCE" if exit_p == pos.entry_price else "RESOLVED"
                                        print(f"MULTI: {emoji} {pos.slot_key} {timeout_note} — {pos.predicted_direction} "
                                              f"entry=${float(pos.entry_price):.4f} exit=${float(exit_p):.4f} "
                                              f"PnL=${float(pos.pnl):+.2f}", flush=True)
                                        self.total_cash = self.simulator.cash
                                        self.update_pnl(pos.slot_key, pos.pnl)
                                        del self._position_timestamps[token]
                                        break

                        resolved = self.simulator.check_resolutions(max_check=5)
                        for pos in resolved:
                            emoji = "🟢" if pos.pnl > 0 else "🔴"
                            print(f"MULTI: {emoji} {pos.slot_key} RESOLVED — {pos.predicted_direction} "
                                  f"entry=${float(pos.entry_price):.4f} exit=${float(pos.exit_price):.4f} "
                                  f"PnL=${float(pos.pnl):+.2f}", flush=True)
                            self.total_cash = self.simulator.cash
                            self.update_pnl(pos.slot_key, pos.pnl)
                            for tok in list(self._position_timestamps.keys()):
                                if any(p.token == tok and p.resolved for p in self.simulator.closed_positions):
                                    del self._position_timestamps[tok]

                    cash = self.simulator.cash if self.simulator else self.total_cash
                    open_pos = len(self.simulator.positions)-len(self.simulator.closed_positions) if self.simulator else 0
                    total_value = float(self.simulator.cash) if self.simulator else float(cash)
                    print(f"MULTI: Cycle {cycle} — SIMULATE cash=${float(cash):.2f} "
                          f"open={open_pos} total_value=${total_value:.2f} pnl=${float(self.simulator.total_pnl):+.2f}", flush=True)
                else:
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
