import asyncio
import threading
import pytest


def test_generation_runs_on_runner_loop_and_preserves_observation():
    from app.live.generation_worker import run_generation_worker
    async def go():
        main_loop=asyncio.get_running_loop();main_thread=threading.get_ident()
        async def work():
            assert asyncio.get_running_loop() is main_loop
            assert threading.get_ident()==main_thread
            return {'observed_ms':1000}
        value,timing=await run_generation_worker(work)
        assert value=={'observed_ms':1000}
        assert timing['submitted_ms']<=timing['generation_started_ms']<=timing['generation_result_ready_ms']<=timing['runner_continued_ms']
        assert timing['continuation_delay_ms']>=0
    asyncio.run(go())


def test_failure_never_becomes_partial_success():
    from app.live.generation_worker import run_generation_worker
    async def fail():raise ValueError('RPC_PARTIAL')
    with pytest.raises(ValueError,match='RPC_PARTIAL'):asyncio.run(run_generation_worker(fail))


def test_cancellation_drains_worker_before_transport_cleanup():
    from app.live.generation_worker import run_generation_worker
    async def go():
        started=threading.Event();release=threading.Event();finished=threading.Event()
        async def work():
            started.set()
            await asyncio.to_thread(release.wait,2)
            finished.set()
        task=asyncio.create_task(run_generation_worker(work))
        await asyncio.to_thread(started.wait,2)
        task.cancel();release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert finished.is_set()
    asyncio.run(go())
