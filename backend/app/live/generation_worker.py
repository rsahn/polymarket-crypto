"""Bounded read-only generation on the runner's existing event loop.
No per-generation event loop, thread handoff, retry, cache, or retiming.
"""
import asyncio
import time
from .latency_trace import mark


def clock_ms():return time.time_ns()//1000000


async def run_generation_worker(factory):
    timing={'submitted_ms':clock_ms(),'execution':'RUNNER_PERSISTENT_EVENT_LOOP',
            'loop_shutdown_before_evaluation':False,'cross_thread_handoff':False}
    async def execute():
        timing['generation_started_ms']=clock_ms()
        value=await factory()
        timing['generation_result_ready_ms']=clock_ms()
        mark('generation.result_ready')
        return value
    task=asyncio.create_task(execute())
    try:
        value=await asyncio.shield(task)
    except asyncio.CancelledError:
        # Drain bounded reads before the caller closes shared HTTP clients.
        while not task.done():
            try:await asyncio.shield(task)
            except asyncio.CancelledError:continue
            except Exception:break
        if task.done() and not task.cancelled():task.exception()
        raise
    timing['runner_continued_ms']=clock_ms()
    mark('generation.runner_continued')
    timing['dispatch_delay_ms']=timing['generation_started_ms']-timing['submitted_ms']
    timing['continuation_delay_ms']=timing['runner_continued_ms']-timing['generation_result_ready_ms']
    return value,timing
