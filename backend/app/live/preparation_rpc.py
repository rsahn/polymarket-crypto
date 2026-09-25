"""Pace preparation reads only; final fixed-C acquisition uses the original RPC.

One in-flight request, >=200 ms between starts, no retry, 120 s dispatch budget.
This conservative local policy is not a claim about the provider's quota.
"""
import threading
import time


class PreparationRPC:
    parallel_inventory_reads = False

    def __init__(self, rpc, *, clock=time.monotonic, sleep=time.sleep, budget_seconds=120):
        self.rpc = rpc
        self.clock, self.sleep = clock, sleep
        self.started = clock()
        self.deadline = self.started + budget_seconds
        self.next_start = self.started
        self.lock = threading.Lock()
        self.count = 0
        self.waited = 0.0
        self.failure = None

    def __getattr__(self, name):
        return getattr(self.rpc, name)

    def call(self, method, params):
        with self.lock:
            if self.failure:
                raise ValueError(self.failure)
            now = self.clock()
            delay = max(0.0, self.next_start - now)
            if now + delay >= self.deadline:
                self.failure = 'PREPARATION_RPC_BUDGET_EXCEEDED'
                raise ValueError(self.failure)
            if delay:
                self.sleep(delay)
                self.waited += delay
            if self.clock() >= self.deadline:
                self.failure = 'PREPARATION_RPC_BUDGET_EXCEEDED'
                raise ValueError(self.failure)
            self.next_start = self.clock() + .2
            self.count += 1
            before = len(getattr(self.rpc, 'calls', []))
            try:
                return self.rpc.call(method, params)
            except Exception:
                # Preparation has one owner and disables scanner fan-out.
                # Read only the audit entry produced by this request.
                entries = getattr(self.rpc, 'calls', [])
                limited = len(entries) > before and entries[-1].get('http_status') == 429
                self.failure = ('PREPARATION_RPC_RATE_LIMITED' if limited else
                                'PREPARATION_RPC_READ_FAILED')
                raise ValueError(self.failure) from None

    def report(self):
        return dict(scope='PREPARATION_ONLY', max_in_flight=1, min_start_interval_ms=200,
                    dispatch_budget_seconds=self.deadline-self.started,
                    requests_started=self.count, pacing_wait_ms=self.waited*1000,
                    retries=0, failure_reason=self.failure)
