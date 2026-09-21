from collections import deque
import math


class BTCFeatures:
    """As-of available time AND source/receive time. Missing coverage stays None."""
    def __init__(self):
        self.ticks = deque()

    def update(self, available_ts_ms, payload):
        price = payload['price']
        if not math.isfinite(price) or price <= 0:
            return
        self.ticks.append((available_ts_ms,payload['recv_ts_ms'],payload.get('event_ts_ms'),price))
        while self.ticks and self.ticks[0][0] < available_ts_ms-60000:
            self.ticks.popleft()

    def at(self, now):
        valid = [x for x in self.ticks if x[0] <= now and x[1] <= now and
                 (x[2] is None or x[2] <= now)]
        current = valid[-1] if valid else None
        result = {'btc_price': current[3] if current else None,
                  'btc_age_ms': now-current[1] if current else None}
        for lag in (250,1000,3000,5000,15000):
            old = next((x for x in reversed(valid) if x[0] <= now-lag and x[1] <= now-lag
                        and (x[2] is None or x[2] <= now-lag)), None)
            tolerance = min(1000, lag)
            usable = current and old and now-current[1] <= tolerance and now-lag-old[1] <= tolerance
            result[f'btc_return_{lag}ms'] = current[3]/old[3]-1 if usable else None
        return result
