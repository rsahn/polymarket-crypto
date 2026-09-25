import asyncio
import threading

def test_generation_reuses_runner_loop_and_never_shuts_it_down(monkeypatch):
    from app.live.generation_worker import run_generation_worker
    async def go():
        loop=asyncio.get_running_loop();thread=threading.get_ident()
        async def work():
            assert asyncio.get_running_loop() is loop
            assert threading.get_ident()==thread
            return {'observed_ms':1000}
        result,t=await run_generation_worker(work)
        assert result['observed_ms']==1000
        assert t['execution']=='RUNNER_PERSISTENT_EVENT_LOOP'
        assert t['loop_shutdown_before_evaluation'] is False
        assert not loop.is_closed()
    asyncio.run(go())

def test_pre_generation_failure_still_emits_blocked_report(monkeypatch):
    import analysis.qualify_post_genesis as q
    def unavailable(*a):raise ValueError('LEDGER_UNAVAILABLE')
    monkeypatch.setattr(q,'read_genesis',unavailable)
    report=asyncio.run(q.run(False))
    assert report['readiness']['submit_allowed'] is False
    assert report['scheduler_timing']['generation_started_ms'] is None
    assert report['scheduler_timing']['post_evaluation_persistence_started_ms']>=report['readiness']['evaluated_ms']
