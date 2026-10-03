"""Offline regressions and actual BTC -> bound V1 -> mocked settlement pipeline."""
import asyncio
import io
import types
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from .core import Journal, CalibrationLedger
from .engine import Coordinator, transient_availability
from .live_logging import LiveLog, LoggedJournal
from .test_calibration import snapshot, signed


def test_self_attestation_cannot_arm():
    from .engine import HumanArm
    from .evidence import SelfAttestingAuthority
    with pytest.raises(ValueError,match='SELF_ATTESTATION_NOT_LIVE_PROOF'):
        HumanArm.confirm('fixture',{},verifier=types.SimpleNamespace(authority=SelfAttestingAuthority()),evidence={})


def fixture(path, mode='full', logged=False, token='t', down='d', maker='account', signer_address='signer'):
    path.mkdir(exist_ok=True)
    now=[1000]
    log=LiveLog(path/'logs','fixture',background=False,console=io.StringIO()) if logged else None
    if log:log.public_tokens.update((token,down));log.public_markets.add('m')
    j=LoggedJournal(path/'journal','fixture',log) if log else Journal(path/'journal','fixture')
    l=CalibrationLedger(j,maker,'500')
    remote={'cash':Decimal('500'),'positions':{},'trades':[],'orders':[]}
    calls=[]
    class Books:
        failure=None
        async def current(self,side):return await self.snapshot(token if side=='UP' else down)
        async def snapshot(self,token):
            if self.failure:raise self.failure
            return dict(valid=True,ws_healthy=True,market='m',token=token,book_state_id=str(now[0]),source_ms=now[0]-1,receive_ms=now[0],asks=[['.5','100']],bids=[['.49','100']])
    class Port:
        signer=signer_address
        # fixture identity
        maker_address=maker
        async def prepare(self,**kw):
            q=Decimal(kw['shares']);p=Decimal(kw['price']);buy=kw['side']=='BUY'
            calls.append('sign')
            return signed(token_id=kw['token'],side=kw['side'],maker_amount=int((Decimal(kw['amount']) if buy else q)*1000000),taker_amount=int((Decimal(kw['amount'])/p if buy else q*p)*1000000))
        async def submit_once(self,cid,order):
            calls.append(cid)
            assert list(Journal.read(j.path))[-1]['kind']=='SEND_DISPATCH_INTENT'
            await asyncio.sleep(0)  # delayed acknowledgement
            return dict(ok=True,order_id=cid+'-remote')
    class Account:
        failure=None
        changes={}
        async def snapshot(self):
            if self.failure:raise self.failure
            return snapshot(l,account=maker,cash=str(remote['cash']),positions=remote['positions'].copy(),trade_ids=remote['trades'].copy(),terminal_order_ids=remote['orders'].copy(),observed_ms=now[0],**self.changes)
        async def execution(self,oid):
            cid=oid.removesuffix('-remote');o=l.orders[cid];buy=o['side']=='BUY'
            q=Decimal('0' if mode=='none' else '10' if mode=='partial' and buy else o['shares'])
            price=Decimal('.5' if buy else '.49');fee=Decimal('.1') if q else Decimal('0')
            fills=[]
            if q:
                tid=oid+'-trade';remote['trades'].append(tid)
                remote['cash']+=(-q*price if buy else q*price)-fee
                remote['positions'][o['token']]=remote['positions'].get(o['token'],Decimal(0))+(q if buy else -q)
                fills=[dict(trade_id=tid,order_id=oid,token=o['token'],market=o['market'],side=o['side'],price=str(price),shares=str(q),cash_fee=str(fee),share_fee='0',fee_evidence=dict(cash_effect_proven=True,share_effect_proven=True),exchange_ts_ms=now[0]-1,receive_ts_ms=now[0])]
            remote['orders'].append(oid)
            # Idempotent duplicate observation must never double debit cash or shares.
            return dict(fills=fills+fills,terminal_status='FILLED' if q==Decimal(o['shares']) else 'CANCELED',cumulative_shares=str(q),account_snapshot=await self.snapshot())
    async def sleep(seconds):now[0]+=int(seconds*1000);await asyncio.sleep(0)
    arm=types.SimpleNamespace(nonce='fixture',started_monotonic=0,check=lambda *a,**k:None)
    port=Port();port.maker=maker
    c=Coordinator(l,port,Account(),Books(),path/'kill',arm=arm,fee_ceiling='1',clock=lambda:now[0],sleep=sleep)
    return c,l,now,log,calls


async def drive(c,now):
    for price in (100,100.1):
        now[0]+=100
        await c.on_btc(types.SimpleNamespace(price=price,event_ts_ms=now[0]-1,recv_ts_ms=now[0]))
    await asyncio.gather(*list(c.v1['pending']))
    await asyncio.sleep(0)


@pytest.mark.parametrize('mode',['full','partial','none'])
def test_btc_to_final_reconciliation(tmp_path,mode):
    c,l,now,log,calls=fixture(tmp_path,mode,logged=True)
    try:
        asyncio.run(drive(c,now))
        assert not l.stop and l.reconciled and l.active is None and not any(l.positions.values())
        assert l.cash==Decimal({'full':'499.3','partial':'499.7','none':'500'}[mode])
        assert l.attempts==1 and l.allocated==26
        assert c.v1['diagnostics']()['V1_SIGNALS']==1
        assert c.v1['diagnostics']()['BTC_TICKS_RECEIVED']==2
        assert c.v1['diagnostics']()['V1_PRIOR_FOUND']==1
        assert len(calls)==(2 if mode=='none' else 4)
        assert len(l.fills)==(0 if mode=='none' else 2)
        assert list(Journal.read(l.journal.path))[-1]['kind']=='OPPORTUNITY_COMPLETE'
    finally:l.journal.close();log.close()


@pytest.mark.parametrize('error',[ValueError('programming error'),KeyError('missing'),ValueError('prefix NO_SHADOW_ENTRY_DEPTH'),ValueError('NO_EXIT_DEPTH')])
def test_unknown_is_not_transient(error):assert not transient_availability(error)


@pytest.mark.parametrize('changes',[{'inventory_proven':False},{'orders_complete':False},{'trades_complete':False},{'positions_complete':False},{'open_orders':['foreign']},{'trade_ids':['foreign']},{'positions':{'foreign':'1'}}])
def test_recovery_requires_complete_account(tmp_path,changes):
    c,l,now,log,calls=fixture(tmp_path)
    # Replace adapter response, not ledger flags.
    async def bad():return snapshot(l,observed_ms=now[0],**changes)
    c.account_source.snapshot=bad;l.stop_new_entries=True
    try:
        assert not asyncio.run(c.recover_entries())
        assert l.stop and l.stop_new_entries and not calls
    finally:l.journal.close()


def test_real_recovery_waits_for_account_book_and_v1(tmp_path):
    c,l,now,log,calls=fixture(tmp_path)
    async def case():
        c.on_status('WS_DISCONNECT')
        c.account_source.failure=ValueError('ACCOUNT_READ_UNAVAILABLE')
        assert not await c.recover_entries()
        c.account_source.failure=None;c.book_source.failure=ValueError('EMPTY_OR_CROSSED_BOOK')
        assert not await c.recover_entries()
        c.book_source.failure=None;c.v1['errors'].append('KeyError')
        assert not await c.recover_entries() and c.v1['errors']==['KeyError']
        c.v1['errors'].clear()  # separate simulated fatal fixture removed explicitly by the test
        assert await c.recover_entries()
        assert l.reconciled and not l.stop_new_entries and c._post_reconnect_verified
    try:asyncio.run(case())
    finally:l.journal.close()


@pytest.mark.parametrize('kind',['CALIBRATION_EXCEPTION','RECOVERY_WAIT','RECOVERY_COMPLETE','BACKGROUND_TASK_ENDED'])
def test_runtime_events_supported_by_real_journal(tmp_path,kind):
    c,l,now,log,calls=fixture(tmp_path,logged=True)
    try:
        l.emit(kind,{'exception_type':'ValueError','message_redacted':'[REDACTED]'})
        assert not l.stop and not l.journal.failed
        assert list(Journal.read(l.journal.path))[-1]['kind']==kind
    finally:l.journal.close();log.close()


def test_journal_failure_original_no_recursion(tmp_path,monkeypatch,capsys):
    c,l,now,log,calls=fixture(tmp_path)
    original=OSError('secret-canary');attempts=[]
    def fail(*a):attempts.append(a);raise original
    monkeypatch.setattr(l.journal,'append',fail)
    try:
        with pytest.raises(OSError) as caught:l.emit('RESERVE',{})
        assert caught.value is original and l.journal_failure is original
        assert l.stop and l.stop_new_entries and not l.reconciled and len(attempts)==1
        assert 'secret-canary' not in capsys.readouterr().err
        assert l.cash==500 and not l.orders and not calls
    finally:l.journal.close()


def test_journal_thread_serialization_and_close(tmp_path):
    j=Journal(tmp_path/'journal','threads')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n:j.append('TEST',{'n':n}),range(160)))
    j.close()
    assert len(list(Journal.read(j.path)))==160
    with pytest.raises(ValueError):j.append('AFTER_CLOSE',{})
    assert j.failed


def test_serialization_failure_latches(tmp_path):
    j=Journal(tmp_path/'journal','serialization')
    with pytest.raises(TypeError):j.append('TEST',{'unsupported':object()})
    assert j.failed and j.seq==0
    with pytest.raises(OSError):j.append('TEST',{})
    j.close()


@pytest.mark.parametrize('error',[TimeoutError('fixture'),KeyError('secret-canary'),RuntimeError('fixture')])
def test_supervisor_background_exception_identity_and_recovery(tmp_path,error):
    from .supervisor import run
    from .custody import CustodyOwner, ReceiptVerifier
    from .test_repairs import Authority
    async def case():
        c,l,now,log,calls=fixture(tmp_path)
        c.sleep=asyncio.sleep;c.arm.started_monotonic=time.monotonic()
        a=Authority()
        class Channel:
            async def accept(self,request):return a.seal(dict(**request,owner='owner',receipt_id='r',accepted_ms=1000))
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner',clock=lambda:1000))
        class Signal:
            attempts=0
            async def run(self,on_tick,on_status):
                self.attempts+=1
                if self.attempts==1:raise error
                await on_tick(types.SimpleNamespace(price=100,event_ts_ms=now[0]-1,recv_ts_ms=now[0]))
                while l.stop_new_entries:await asyncio.sleep(.01)
                l.halt('MANUAL_KILL')
                await asyncio.Event().wait()
        class Book:
            async def run(self,*a):await asyncio.Event().wait()
        source=Signal()
        try:
            if isinstance(error,TimeoutError):
                await asyncio.wait_for(run(c,source,Book(),tmp_path/'reports',owner),4)
                assert source.attempts==2
                assert any(r['kind']=='RECOVERY_COMPLETE' for r in Journal.read(l.journal.path))
            else:
                with pytest.raises(type(error)) as raised:
                    await asyncio.wait_for(run(c,source,Book(),tmp_path/'reports',owner),4)
                assert raised.value is error and source.attempts==1 and l.stop
                await owner.wait_resolved()
            assert not calls and not l.orders
            assert 'secret-canary' not in l.journal.path.read_text()
        finally:l.journal.close()
    asyncio.run(case())


def test_book_rotation_and_seed_failure_are_real_calls(tmp_path):
    from .adapters import BookAdapter
    from app.live.readonly_book_stream import StreamBook
    async def case():
        stream=StreamBook('old','m',('t','d'),9000,clock=lambda:1000)
        adapter=BookAdapter(stream,market='m',tokens={'UP':'t','DOWN':'d'},clock=lambda:1000)
        async def failure():raise TimeoutError('fixture reseed')
        with pytest.raises(TimeoutError):
            await adapter.rotate('new','new-condition',('1','2'),19000,rest_seed_coro=failure)
        assert adapter.market=='new-condition' and adapter.tokens=={'UP':'1','DOWN':'2'}
        assert adapter.state=='INITIALIZING' and not adapter.ready.is_set()
        assert adapter.stream.expected_tokens==('1','2')
    asyncio.run(case())


def test_stream_cannot_start_twice_during_backoff():
    from app.live.readonly_book_stream import StreamBook
    async def case():
        stream=StreamBook('old','m',('t','d'),9000,clock=lambda:1000)
        class Socket:
            async def __aenter__(self):raise OSError('fixture')
            async def __aexit__(self,*a):pass
        task=asyncio.create_task(stream.run(connect_factory=lambda *a,**k:Socket()))
        try:
            async def failed():
                while stream.failure is None:await asyncio.sleep(0)
            await asyncio.wait_for(failed(),1)
            with pytest.raises(RuntimeError,match='BOOK_STREAM_ALREADY_RUNNING'):
                await stream.run(connect_factory=lambda *a,**k:Socket())
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        assert not stream._run_active and not stream.read()['available']
    asyncio.run(case())


def test_72h_logical_multiple_capped_sessions(tmp_path):
    """72 one-hour sessions: 864 disconnect/requalification cycles, 144 orders.

    Multiple sessions are essential: the immutable four-entry/$100 cap prevents
    a single live experiment from legitimately generating unlimited orders.
    This is accelerated coordinator coverage, not 72h of real WS availability.
    """
    async def case():
        elapsed=0;orders=0;rotations=0;account_failures=0
        for hour in range(72):
            c,l,now,log,calls=fixture(tmp_path/str(hour))
            try:
                for cycle in range(12):
                    c.on_status('WS_DISCONNECT')
                    c.account_source.failure=TimeoutError('synthetic')
                    assert not await c.recover_entries();account_failures+=1
                    c.account_source.failure=None
                    assert await c.recover_entries()
                    now[0]+=300000;elapsed+=300;rotations+=1
                await drive(c,now)
                assert l.reconciled and not l.stop and l.active is None
                assert not any(l.positions.values()) and l.attempts==1 and l.allocated<=100
                orders+=len(l.orders)
                assert len(list(Journal.read(l.journal.path)))>30
            finally:l.journal.close()
        assert elapsed==259200 and rotations==864 and account_failures==864 and orders==144
    asyncio.run(case())
