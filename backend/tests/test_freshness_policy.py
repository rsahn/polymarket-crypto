import asyncio
import pytest
from app.live.freshness_policy import freshness_policy, freshness_limit_ms
from app.live.production_readonly import fresh, BookStateSource
from app.live.fixed_boundary import evaluate_boundary
from test_fixed_boundary import evidence


def test_authorized_boundaries_and_no_retiming():
    assert freshness_limit_ms()==500
    with freshness_policy(1300):
        assert fresh(1000,1500)
        assert not fresh(1000,1501)
        assert not fresh(1000,2300)
        assert not fresh(1000,2301)
        assert not fresh(1001,1000)
        e=evidence(); before=dict(e)
        value=evaluate_boundary(e,now=1500)
        assert value['boundary_generation_complete']
        assert not value['current_inventory_proven']
        assert e==before
        assert evaluate_boundary(e,now=2301)['reason']=='GENERATION_STALE_500MS'
    assert not fresh(1000,1501)


@pytest.mark.parametrize('value',[True,0,1301,500.0,'1300',None])
def test_unapproved_or_ambiguous_policy_rejected(value):
    with pytest.raises(ValueError):
        with freshness_policy(value):pass


def test_policy_propagates_to_workers_without_cross_task_contamination():
    async def task(limit):
        with freshness_policy(limit):
            await asyncio.sleep(0)
            return await asyncio.to_thread(freshness_limit_ms)
    async def run():return await asyncio.gather(task(500),task(1300))
    assert asyncio.run(run())==[500,1300]
    assert freshness_limit_ms()==500


def test_book_retains_own_limit_despite_legacy_context():
    with freshness_policy(1300):
        book=BookStateSource(clock=lambda:1500)
        book.connect('market',('a','b'),1)
        for token in ('a','b'):book.update(token,[(.4,2)],[(.5,2)],1000,1)
        assert book.read()['available']
        book.clock=lambda:1501
        assert not book.read()['available']


def test_execution_and_staged_gate_cannot_be_relaxed_by_legacy_policy(tmp_path):
    from test_execution_controller import Fixture, order
    from app.live.execution import ExecutionBlocked
    from app.live.clob_staged import BookFreshnessGate
    f=Fixture(tmp_path/'test.db')
    try:
        with freshness_policy(1300):
            gate=BookFreshnessGate()
            assert gate.max_book_age_ms==500
            f.controller.clock=lambda:1500
            f.controller.gates(order())
            assert asyncio.run(f.controller.account())['observed_ms']==1000
            f.controller.clock=lambda:1501
            with pytest.raises(ExecutionBlocked):f.controller.gates(order())
            with pytest.raises(ExecutionBlocked):asyncio.run(f.controller.account())
    finally:f.store.close()


def test_account_completeness_is_not_relaxed_by_freshness(tmp_path):
    from test_execution_controller import Fixture
    from app.live.execution import ExecutionBlocked
    f=Fixture(tmp_path/'test.db')
    async def incomplete():return dict(complete=False,observed_ms=1000,open_order_ids=[],balances={})
    f.controller.account_reader=incomplete
    try:
        with freshness_policy(1300):
            with pytest.raises(ExecutionBlocked,match='ACCOUNT_EVIDENCE_INCOMPLETE'):
                asyncio.run(f.controller.recover())
        assert not f.calls
    finally:f.store.close()


@pytest.mark.parametrize('limit',[500,1300])
def test_manual_runner_rejects_global_policy_before_any_read(monkeypatch,tmp_path,capsys,limit):
    import analysis.qualify_post_genesis as q
    async def forbidden(*a,**kw):raise AssertionError('must not start qualification')
    monkeypatch.setattr(q,'run',forbidden)
    monkeypatch.setattr(q,'ROOT',tmp_path)
    monkeypatch.setattr(q.sys,'argv',['probe','--target-machine','--health-contract','--freshness-ms',str(limit)])
    assert q.main()==2
    assert list(tmp_path.iterdir())==[]
    assert 'GLOBAL_FRESHNESS_OVERRIDE_RETIRED' in capsys.readouterr().out
    assert freshness_limit_ms()==500
