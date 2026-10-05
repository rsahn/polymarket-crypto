"""Generic V1 strategy evaluator — one per crypto.

Replicates the core V1 logic without depending on the hash-locked binding:
- Maintains a price tick window (deque, 4096 entries)
- Detects price moves > 0.05% within a 250ms lookback
- Generates BUY/SELL signals with direction and move magnitude
"""
import time
from collections import deque
from decimal import Decimal


class V1Strategy:
    """Per-crypto strategy evaluator mirroring the V1 BTC logic."""

    # Threshold from V1: 0.05% price move triggers signal
    MOVE_THRESHOLD = Decimal("0.0005")

    def __init__(self, symbol: str, on_opportunity=None):
        self.symbol = symbol
        self.on_opportunity = on_opportunity  # async callback(signal_ts, move, side)
        self.tick_window = deque(maxlen=4096)
        self.last_receive_ms = None
        self.metrics = {
            'TICKS': 0,
            'EVALUATIONS': 0,
            'SIGNALS': 0,
            'LAST_TICK_MS': None,
        }

    async def on_tick(self, tick):
        """Process a price tick from Binance (or any price feed).

        tick must have: event_ts_ms, recv_ts_ms, price
        """
        if tick.event_ts_ms is None or tick.recv_ts_ms is None:
            return

        self.metrics['TICKS'] += 1
        self.metrics['LAST_TICK_MS'] = tick.recv_ts_ms

        self.tick_window.append({
            'source_ms': tick.event_ts_ms,
            'receive_ms': tick.recv_ts_ms,
            'price': tick.price,
        })

        await self._evaluate(tick)

    async def _evaluate(self, tick):
        """Evaluate whether the current tick triggers a signal.

        V1 logic: look back 250ms, compare current price to the prior tick.
        If |move| > 0.05%, signal direction.
        """
        self.metrics['EVALUATIONS'] += 1

        # Find a prior tick within the 250ms lookback window
        prior = None
        for entry in self.tick_window:
            if entry['source_ms'] >= tick.recv_ts_ms - 250 and entry['source_ms'] < tick.recv_ts_ms:
                prior = entry
                break

        if prior is None:
            return  # Not enough history

        current_price = Decimal(str(tick.price))
        prior_price = Decimal(str(prior['price']))

        if prior_price == 0:
            return

        move = (current_price - prior_price) / prior_price

        if abs(move) <= self.MOVE_THRESHOLD:
            return  # Move too small

        # Signal!
        side = "BUY" if move > 0 else "SELL"
        self.metrics['SIGNALS'] += 1

        signal_ts = tick.recv_ts_ms
        btc_move = float(move * 100)  # percentage

        if self.on_opportunity:
            await self.on_opportunity(signal_ts, btc_move, side)

    def diagnostics(self):
        """Return metrics for logging."""
        values = sorted(
            [self.tick_window[i+1]['receive_ms'] - self.tick_window[i]['receive_ms']
             for i in range(len(self.tick_window) - 1)]
        )
        p50 = values[int(len(values) * 0.50)] if values else None
        p95 = values[int(len(values) * 0.95)] if values else None
        return {
            **self.metrics,
            'WINDOW_SIZE': len(self.tick_window),
            'INTERVAL_P50_MS': p50,
            'INTERVAL_P95_MS': p95,
        }
