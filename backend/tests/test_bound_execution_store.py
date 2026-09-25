import asyncio
from decimal import Decimal
import sqlite3
import pytest
from app.live.genesis_ledger import create_genesis,digest,append_activity
from test_genesis_ledger import evidence
from app.live.bound_execution_store import BoundExecutionStore
from app.live.execution import ExecutionBlocked


@pytest.fixture
def paths(tmp_path):
    genesis=tmp_path/'genesis.db';snapshot=evidence()
    assert create_genesis(genesis,snapshot,now_ms=1001)['created']
    return genesis,tmp_path/'session.db',digest(snapshot)


def open_store(paths,create=False):
    g,s,h=paths
    return BoundExecutionStore(s,genesis_path=g,expected_genesis_hash=h,create=create)


def test_session_cycle_and_restart_leave_genesis_byte_identical(paths):
    from test_execution_controller import Fixture
    before=paths[0].read_bytes()
    f=Fixture(paths[1].with_name('fixture.db'));f.store.close()
    f.store=open_store(paths,True);f.controller.store=f.store
    try:
        result=asyncio.run(f.run())
        assert result['phase']=='CLOSED'
    finally:f.store.close()
    with open_store(paths) as store:
        assert store.load()['phase']=='CLOSED'
        assert Decimal(store.projection()['open_shares'])==0
        assert not store.projection()['cash_reconciled']
        assert not store.projection()['submit_allowed']
    assert paths[0].read_bytes()==before


@pytest.mark.parametrize('kind',['state','event','chain','deletion'])
def test_tampering_is_rejected(paths,kind):
    with open_store(paths,True) as store:
        store.write('ENTRY_INTENT',{'phase':'ENTRY_SUBMIT_PENDING'},reserve=True)
    with sqlite3.connect(paths[1]) as db:
        sql={'state':"UPDATE execution_state SET value='{}'",
             'event':"UPDATE execution_events SET event='FAKE'",
             'chain':"UPDATE execution_chain SET hash='bad'",
             'deletion':'DELETE FROM execution_events'}[kind]
        db.execute(sql)
    with pytest.raises(ExecutionBlocked):open_store(paths)


def test_write_failure_rolls_back_state_event_and_hash(paths):
    with open_store(paths,True) as store:
        store.db.execute("CREATE TRIGGER fail_chain BEFORE INSERT ON execution_chain BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with pytest.raises(sqlite3.DatabaseError):store.write('ENTRY_INTENT',{'phase':'ENTRY_SUBMIT_PENDING'},reserve=True)
        assert store.load() is None
        assert store.db.execute('select count(*) from execution_events').fetchone()[0]==0


def test_second_process_cannot_reserve_and_file_never_overwritten(paths):
    with open_store(paths,True) as first,open_store(paths) as second:
        first.write('ENTRY_INTENT',{'phase':'ENTRY_SUBMIT_PENDING'},reserve=True)
        with pytest.raises(ExecutionBlocked):second.write('ENTRY_INTENT',{'phase':'ENTRY_SUBMIT_PENDING'},reserve=True)
    before=paths[1].read_bytes()
    with pytest.raises(FileExistsError):open_store(paths,True)
    assert paths[1].read_bytes()==before


def test_genesis_binding_change_blocks_new_activity(paths):
    with open_store(paths,True) as store:
        append_activity(paths[0],'RECOVERY_REQUIRED',{'reason':'fixture'},now_ms=1002)
        with pytest.raises(ExecutionBlocked):store.write('ENTRY_INTENT',{'phase':'ENTRY_SUBMIT_PENDING'},reserve=True)


def test_wrong_genesis_never_creates_session(paths):
    with pytest.raises(ExecutionBlocked):BoundExecutionStore(paths[1],genesis_path=paths[0],expected_genesis_hash='f'*64,create=True)
    assert not paths[1].exists()


def test_genesis_path_cannot_be_used_as_session(paths):
    before=paths[0].read_bytes()
    with pytest.raises(ExecutionBlocked):BoundExecutionStore(paths[0],genesis_path=paths[0],expected_genesis_hash=paths[2],create=True)
    assert paths[0].read_bytes()==before


def test_publication_interruption_leaves_no_session_or_temp(paths,monkeypatch):
    import app.live.bound_execution_store as module
    def fail(*args):raise OSError('simulated interruption')
    monkeypatch.setattr(module.os,'link',fail)
    with pytest.raises(OSError):open_store(paths,True)
    assert not paths[1].exists()
    assert not list(paths[1].parent.glob('d6-session-*.tmp'))


def test_live_binding_tamper_detected_before_write(paths):
    with open_store(paths,True) as store:
        store.db.execute("UPDATE session_binding SET value='{}'")
        with pytest.raises(ExecutionBlocked):store.write('ENTRY_INTENT',{'phase':'ENTRY_SUBMIT_PENDING'},reserve=True)
        assert store.db.execute('SELECT count(*) FROM execution_events').fetchone()[0]==0


def test_cash_observation_is_journaled_without_inventing_risk_clearance(paths):
    from test_cash_evidence import evidence as cash_fixture,TX
    from app.live.genesis_ledger import read_genesis
    prior=read_genesis(paths[0])['snapshot'];e=cash_fixture()
    e['wallet']=prior['wallet'];e['collateral_contract']=prior['collateral']['contract']
    e['before'].update(block_number=42,block_hash=prior['block_hash'])
    e['after']['block_number']=43
    e['canonical_blocks']={'42':prior['block_hash'],'43':e['after']['block_hash']}
    receipt=e['receipts'][0]['receipt'];receipt['blockNumber']='0x2b'
    log=receipt['logs'][0];log['blockNumber']='0x2b';log['address']=e['collateral_contract']
    log['topics'][1]='0x'+'0'*24+e['wallet'][2:]
    with open_store(paths,True) as store:
        store.write('FLAT_VERIFIED',dict(phase='CLOSED',bought=0,sold=0))
        e['debug']={'passphrase':'fixture-not-a-real-credential'}
        result=store.record_cash_observation(e,expected_transactions=[TX],now_ms=1100)
        assert result['status']=='CASH_DELTA_MATCHED'
        projection=store.projection()
        assert projection['cash_delta_status']=='CASH_DELTA_MATCHED'
        assert not projection['cash_reconciled'] and projection['fees'] is None
        assert 'debug' not in store.load()['cash_observation']['evidence']
        assert 'fixture-not-a-real-credential' not in str(store.load())
        assert store.db.execute('select event from execution_events order by id desc limit 1').fetchone()[0]=='CASH_DELTA_OBSERVATION'


def test_cash_recording_requires_a_closed_recorded_cycle(paths):
    with open_store(paths,True) as store:
        with pytest.raises(ExecutionBlocked):store.record_cash_observation({},expected_transactions=[],now_ms=1000)
        assert store.load() is None


def test_observation_cannot_overwrite_a_concurrent_new_intent(paths):
    with open_store(paths,True) as first,open_store(paths) as second:
        first.write('FLAT_VERIFIED',dict(phase='CLOSED',bought=0,sold=0))
        old=first.load()
        second.write('ENTRY_INTENT',dict(phase='ENTRY_SUBMIT_PENDING'),reserve=True)
        with pytest.raises(ExecutionBlocked,match='SESSION_CHANGED'):
            first.write('CASH_DELTA_OBSERVATION',old,expected_state=old)
        assert first.load()['phase']=='ENTRY_SUBMIT_PENDING'
