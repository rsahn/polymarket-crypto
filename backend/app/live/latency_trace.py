"""Opt-in bounded timing evidence. Never records arguments, payloads or credentials.

Monotonic times explain intervals; UTC anchors correlate existing reports.
Thread CPU is recorded only across synchronous code, never across an await.
This observes application receipt, not kernel/network arrival or GIL ownership.
"""
import asyncio
import contextvars
import functools
import time
from collections import deque

active_trace = contextvars.ContextVar('d6_latency_trace', default=None)


class Trace:
    def __init__(self, limit=20000):
        self.events = deque(maxlen=limit)
        self.dropped = 0
        self.utc_anchor_ms = time.time_ns() // 1000000
        self.monotonic_anchor_ns = time.perf_counter_ns()

    def add(self, event):
        # Only loop-thread callers publish completed events.
        if len(self.events) == self.events.maxlen:
            self.dropped += 1
        self.events.append(event)

    def report(self):
        return dict(utc_anchor_ms=self.utc_anchor_ms,
                    monotonic_anchor_ns=self.monotonic_anchor_ns,
                    events=list(self.events), dropped_events=self.dropped,
                    scope='APPLICATION_TIMING_NOT_NETWORK_ARRIVAL_OR_GIL_PROOF',
                    enabled=True)


def mark(label):
    trace=active_trace.get()
    if trace is not None:
        trace.add(dict(kind='instant',label=label,at_ns=time.perf_counter_ns()))


def sync_span(label):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            trace = active_trace.get()
            if trace is None:
                return fn(*args, **kwargs)
            start = time.perf_counter_ns()
            cpu = time.thread_time_ns()
            try:
                return fn(*args, **kwargs)
            finally:
                end = time.perf_counter_ns()
                trace.add(dict(kind='sync', label=label, start_ns=start, end_ns=end,
                               wall_ms=(end-start)/1e6,
                               thread_cpu_ms=(time.thread_time_ns()-cpu)/1e6))
        return wrapped
    return decorate


async def measured_thread(label, fn, *args, **kwargs):
    trace = active_trace.get()
    if trace is None:
        return await asyncio.to_thread(fn, *args, **kwargs)
    event = dict(kind='worker', label=label, dispatch_ns=time.perf_counter_ns())
    def work():
        event['worker_start_ns'] = time.perf_counter_ns()
        cpu = time.thread_time_ns()
        try:
            return fn(*args, **kwargs)
        finally:
            event['worker_end_ns'] = time.perf_counter_ns()
            event['thread_cpu_ms'] = (time.thread_time_ns()-cpu)/1e6
    try:
        return await asyncio.to_thread(work)
    finally:
        event['resume_ns'] = time.perf_counter_ns()
        # Cancellation may precede worker completion. Do not invent an end time.
        event = dict(event)
        if 'worker_end_ns' in event:
            event.update(queue_ms=(event['worker_start_ns']-event['dispatch_ns'])/1e6,
                         worker_ms=(event['worker_end_ns']-event['worker_start_ns'])/1e6,
                         resume_ms=(event['resume_ns']-event['worker_end_ns'])/1e6)
        else:
            event['incomplete_at_resume'] = True
        trace.add(event)


async def measured_await(label, awaitable):
    trace = active_trace.get()
    if trace is None:
        return await awaitable
    start = time.perf_counter_ns()
    try:
        return await awaitable
    finally:
        end = time.perf_counter_ns()
        trace.add(dict(kind='await', label=label, start_ns=start, end_ns=end,
                       wall_ms=(end-start)/1e6))


def diagnose(fn):
    @functools.wraps(fn)
    async def wrapped(*args, **kwargs):
        trace = Trace()
        token = active_trace.set(trace)
        loop = asyncio.get_running_loop()
        handle = None
        def tick(due):
            nonlocal handle
            current = loop.time()
            trace.add(dict(kind='loop_lag', label='loop.timer',
                           at_ns=time.perf_counter_ns(), lag_ms=max(0,current-due)*1000))
            due = current + .01
            handle = loop.call_at(due, tick, due)
        due = loop.time() + .01
        handle = loop.call_at(due, tick, due)
        try:
            result = await fn(*args, **kwargs)
            return {**result, 'latency_diagnostics': trace.report()}
        finally:
            if handle is not None:
                handle.cancel()
            active_trace.reset(token)
    return wrapped
