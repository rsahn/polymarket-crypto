import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor


def test_thread_queue_and_resume_are_distinct():
    from app.live.latency_trace import diagnose, measured_thread
    async def scenario():
        loop = asyncio.get_running_loop()
        pool = ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(pool)
        entered = threading.Event()
        release = threading.Event()
        occupied = loop.run_in_executor(None, lambda: (entered.set(), release.wait(2)))
        assert entered.wait(1)
        loop.call_later(.04, release.set)
        value = await measured_thread('test.worker', lambda: 42)
        await occupied
        return {'value': value}
    report = asyncio.run(diagnose(scenario)())
    row = next(x for x in report['latency_diagnostics']['events'] if x['label']=='test.worker')
    assert report['value']==42
    assert row['dispatch_ns'] <= row['worker_start_ns'] <= row['worker_end_ns'] <= row['resume_ns']
    assert row['queue_ms'] >= 20
    assert row['worker_ms'] < row['queue_ms']


def test_sync_cpu_is_separate_from_await_and_payload_is_not_recorded():
    from app.live.latency_trace import diagnose, sync_span, measured_thread
    @sync_span('test.cpu')
    def work(secret):
        return sum(i*i for i in range(100000))
    async def scenario():
        work('PRIVATE_PAYLOAD')
        await measured_thread('test.error', lambda: 1/0)
    # Exceptions propagate; successful diagnosis must not swallow business failures.
    import pytest
    with pytest.raises(ZeroDivisionError):
        asyncio.run(diagnose(scenario)())
    async def success():
        work('PRIVATE_PAYLOAD')
        return {}
    report = asyncio.run(diagnose(success)())
    import json
    assert 'PRIVATE_PAYLOAD' not in json.dumps(report)
    event = next(x for x in report['latency_diagnostics']['events'] if x['label']=='test.cpu')
    assert event['wall_ms'] >= 0 and event['thread_cpu_ms'] >= 0


def test_diagnostics_bounded_and_context_restored():
    from app.live.latency_trace import Trace, active_trace, diagnose
    t=Trace(limit=2)
    for i in range(5): t.add({'label':'test','i':i})
    assert len(t.events)==2 and t.dropped==3
    async def scenario():
        assert active_trace.get() is not None
        return {}
    asyncio.run(diagnose(scenario)())
    assert active_trace.get() is None
