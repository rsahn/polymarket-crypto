from collections import deque

class LatencyTracker:
    def __init__(self, maxlen=10000):
        self.impulses = deque(maxlen=maxlen)

    def btc_impulse(self, ts_ms: int, return_bps: float):
        self.impulses.append((ts_ms, return_bps))

    def match_poly_move(self, ts_ms: int, direction: int):
        for btc_ts, bps in reversed(self.impulses):
            if (bps > 0) == (direction > 0):
                return ts_ms - btc_ts
        return None
