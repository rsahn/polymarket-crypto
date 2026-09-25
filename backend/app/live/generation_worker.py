"""One bounded read-only generation on an event loop independent of the WS reader.
No retries, snapshot cache, permanent worker, or freshness adjustments.
"""
import asyncio
import time


def clock_ms():return time.time_ns()//1000000


async def run_generation_worker(factory):
    timing={'submitted_ms':clock_ms(),'execution':'ISOLATED_GENERATION_EVENT_LOOP'}
    def execute():
        timing['worker_started_ms']=clock_ms()
        async def run():
            value=await factory()
            timing['worker_result_ready_ms']=clock_ms()
            return value
        result=asyncio.run(run())
        timing['worker_finished_ms']=clock_ms()
        return result
    task=asyncio.create_task(asyncio.to_thread(execute))
    try:
        value=await asyncio.shield(task)
    except asyncio.CancelledError:
        # A running to_thread cannot be killed. Drain it before callers close
        # shared HTTP pools; never leave detached reads using closed transports.
        while not task.done():
            try:await asyncio.shield(task)
            except asyncio.CancelledError:continue
            except Exception:break
        if task.done() and not task.cancelled():task.exception()
        raise
    timing['main_resumed_ms']=clock_ms()
    timing['dispatch_delay_ms']=timing['worker_started_ms']-timing['submitted_ms']
    timing['loop_shutdown_ms']=timing['worker_finished_ms']-timing['worker_result_ready_ms']
    timing['main_resume_delay_ms']=timing['main_resumed_ms']-timing['worker_finished_ms']
    return value,timing
