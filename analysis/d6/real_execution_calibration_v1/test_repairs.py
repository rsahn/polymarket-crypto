import asyncio,copy,io,time,types
import pytest
from .core import digest
from .qualification import EvidenceVerifier,FeeRisk
from .preflight import evaluate,REQUIRED
from .v1_binding import verify
from .custody import ReceiptVerifier,CustodyOwner
from .test_calibration import ledger,intent,fill

class Authority:
    def __init__(self):self.allowed=set()
    def seal(self,row):self.allowed.add(digest(row));return row
    def verify(self,row):return digest(row) in self.allowed
    def verify_client(self,client,record):return client is getattr(self,'client',None) and self.verify(record)
    def verify_bindings(self,bindings,proof):
        if not hasattr(self,'bindings'):self.bindings=bindings
        return all(a is b for a,b in zip(self.bindings,bindings))
    async def verify_durable(self,row):return self.verify(row)

def evidence():
    a=Authority();v=EvidenceVerifier(a,account='account',market='m',session='experiment',collateral='pUSD',strategy_hashes=verify())
    h='a'*64
    payloads=[dict(wallet='account',maker='account',signer='s'),dict(available_cash='100',required_cash='100',collateral='pUSD'),dict(condition='m',tokens=['u','d'],outcome_tokens={'UP':'u','DOWN':'d'},expires_ms=9000),dict(sdk_version='0.11.0',codec_digest=h,http_attempts=1,allowance_mutation=False),dict(scope='wallet',atomic_frontier={'sequence':1,'digest':'b'*64},baseline_digest=h,fee_effects='cash_and_shares'),dict(cash_collateral='1',outcome_shares='1',collateral_per_share_upper='1',fee_source_digest=h,coverage='ROUND_TRIP_FAK_1BUY_1SELL',epoch='fixture',late_fill_coverage=True),dict(owner='operator',channel='external',durable_receipt_probe='remote'),dict(verified_sequence=1,journal_digest=h,free_bytes=2**40),dict(test_digest=h,new_entries_after_kill=0,custody_verified=True),dict(test_digest=h,independent_observations=True,unknown_events_rejected=True),dict(offset_ms=0,uncertainty_ms=1),dict(state='SYNCHRONIZED',generation=1,tokens=['u','d'],receive_ms=1000),dict(test_digest=h,failed=0,passed=1),dict(audit_digest=h,reviewer='independent',unresolved_critical=0)]
    e={'observed_ms':1000}
    for k,p in zip(REQUIRED,payloads):e[k]=a.seal(dict(**v.context,check=k,payload=p,source_digest=digest(p),observed_ms=1000,valid_until_ms=2000))
    return a,v,e

@pytest.mark.parametrize('stubborn',[False,True])
def test_complete_injected_composition_without_order_calls(tmp_path,stubborn):
    from .runner import PreparedSession
    from .transport import SDKPort
    async def case():
        a,v,e=evidence();a.client=object()
        base=a.seal(dict(account='account',session='experiment',collateral='pUSD',atomic_frontier={'sequence':0,'digest':'b'*64},trade_ids=[],valid_until_ms=2000))
        e['account_evidence_adapter_qualified']['payload']['baseline_digest']=digest(base)
        e['account_evidence_adapter_qualified']['source_digest']=digest(e['account_evidence_adapter_qualified']['payload']);a.seal(e['account_evidence_adapter_qualified'])
        e['exit_handoff_ready']['payload']['owner']='owner';e['exit_handoff_ready']['source_digest']=digest(e['exit_handoff_ready']['payload']);a.seal(e['exit_handoff_ready'])
        release=asyncio.Event()
        class Stream:
            tokens=('u','d');generation=1
            def read(self):return {'available':True,'fresh':True,'book_synced':True,'generation':1}
            async def run(self,*,rest_seed_coro=None):
                while not release.is_set():
                    try:await release.wait()
                    except asyncio.CancelledError:
                        if not stubborn:raise
        class Channel:
            async def accept(self,req):return a.seal(dict(**req,owner='owner',receipt_id='r',accepted_ms=1000))
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner',clock=lambda:1000))
        s=PreparedSession(directory=tmp_path,experiment_id='experiment',account='account',starting_cash='100',account_reader=None,position_reader=None,stream=Stream(),market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:1000,collateral='pUSD',baseline=base)
        class Signal:
            async def run(self,*args):raise RuntimeError('fixture_end_no_order')
        async def monitor_fixture():await asyncio.Event().wait()
        s.coordinator.monitor_account=monitor_fixture
        s.ledger.reconciled=True
        arm=types.SimpleNamespace(nonce='fixture',started_monotonic=time.monotonic(),check=lambda *a:None)
        try:
            with pytest.raises(RuntimeError,match='fixture_end'):await s.start(client=a.client,verifier=v,evidence=lambda:e,signal_source=Signal(),custody_owner=owner,confirm=lambda *a,**k:arm)
            assert isinstance(s.coordinator.port,SDKPort) and not s.ledger.orders and owner.accepted
            if stubborn:assert any('ROOT_STREAM_CLEANUP' in error for error in owner.errors)
        finally:
            release.set();await asyncio.sleep(0)
            if owner.tasks:await asyncio.wait(owner.tasks,timeout=1)
            s.close()
    asyncio.run(case())

def test_semantic_preflight_can_pass_only_authenticated_fixture():
    a,v,e=evidence();assert evaluate(e,1000,2**40,v)['status']=='CALIBRATION_READY'
    for k in REQUIRED:
        bad=copy.deepcopy(e);bad[k]['payload']['untrusted']=True
        assert k in evaluate(bad,1000,2**40,v)['blockers']
    assert evaluate(e,6001,2**40,v)['status']=='CALIBRATION_BLOCKED'

@pytest.mark.parametrize('cash,shares,conversion,expiry,ok',[('.1','.2','1',2000,True),('.1','0',None,2000,True),('1','2','1',2000,False),('.1','.2',None,2000,False),('.1','.2','1',999,True)])
def test_fee_risk_preserves_native_observations(tmp_path,cash,shares,conversion,expiry,ok):
    l=ledger(tmp_path);l.seal_shadow('op',{'market':'m','token':'t'})
    risk=FeeRisk('1','0' if shares=='0' else '1',conversion,'a'*64,'m',expiry)
    l.reserve('op','25','2',fee_risk=risk);intent(l)
    try:
        assert fill(l,fee=cash,sf=shares)==ok
        assert l.share_fees==__import__('decimal').Decimal(shares)
        assert l.positions['t']==50-__import__('decimal').Decimal(shares)
    finally:l.journal.close()

def test_account_independent_execution_and_foreign_baseline():
    from .adapters import AccountAdapter
    a=Authority();base=a.seal(dict(account='account',session='experiment',collateral='pUSD',atomic_frontier={'sequence':0,'digest':'b'*64},trade_ids=['old'],valid_until_ms=2000))
    common=dict(account='account',session='experiment',collateral='pUSD',scope='wallet',atomic_frontier={'sequence':1,'digest':'b'*64},ancestor_frontiers=[base['atomic_frontier']],observed_ms=1000,baseline_digest=digest(base))
    snap=a.seal(dict(**common,cash='99',positions={'u':'2'},trade_ids=['old','new'],experiment_trade_ids=['new'],terminal_order_ids=['o'],open_orders=[],**dict.fromkeys(('inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete'),True)))
    f=dict(trade_id='new',order_id='o',token='u',market='m',side='BUY',price='.5',shares='2',cash_fee='0',share_fee='0',fee_evidence=dict(cash_effect_proven=True,share_effect_proven=True),exchange_ts_ms=999,receive_ts_ms=1000)
    e=a.seal(dict(**common,order_id='o',schema='independent-settled/v1',market='m',token='u',side='BUY',fills=[f],terminal_status='FILLED',cumulative_shares='2',account_snapshot=snap))
    class Source:
        async def snapshot(self):return copy.deepcopy(snap)
        async def execution(self,oid):return copy.deepcopy(e)
    adapter=AccountAdapter(None,None,account='account',collateral='pUSD',evidence_source=Source(),authority=a,baseline=base,session='experiment',intents=lambda:{'local':{'order_id':'o','market':'m','token':'u','side':'BUY'}},clock=lambda:1000)
    assert asyncio.run(adapter.execution('o'))['account_snapshot']['trade_ids']==['new']
    for change in (dict(account='other'),dict(collateral='other'),dict(atomic_frontier=None),dict(trade_ids=['old','new','foreign'])):
        bad=a.seal({**snap,**change})
        with pytest.raises(ValueError):adapter.normalize_snapshot(bad)

def test_receipt_external_auth_identity_replay():
    async def case():
        a=Authority();v=ReceiptVerifier(a,'owner',clock=lambda:1000)
        req=dict(account='a',experiment_id='e',exposure_digest='a'*64,journal_sequence=3)
        r=dict(**req,owner='owner',receipt_id='r',accepted_ms=1000)
        assert not await v.verify(r,req)
        a.seal(r)
        for field in ('owner','account','exposure_digest','journal_sequence'):
            bad={**r,field:'wrong'};a.seal(bad);assert not await v.verify(bad,req)
        assert await v.verify(r,req);assert not await v.verify(r,req)
    asyncio.run(case())

def test_journal_failure_does_not_drop_independent_custody(tmp_path):
    from .supervisor import run
    async def case():
        l=ledger(tmp_path);l.reconciled=False;l.journal.failed=True
        class C:
            ledger=l;busy=False;v1={'pending':[],'errors':[]};comparisons=[];kill_path=tmp_path/'stop';arm=types.SimpleNamespace(started_monotonic=time.monotonic())
            def guard(self):pass
            async def on_btc(self,*a):pass
            def on_status(self,*a):pass
            async def monitor_account(self):raise OSError('dead_monitor')
        a=Authority()
        class Channel:
            async def accept(self,req):return a.seal(dict(**req,owner='owner',receipt_id='id',accepted_ms=1000))
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner',clock=lambda:1000),timeout=.1)
        class Feed:
            async def run(self,*a):raise RuntimeError('primary')
        try:
            with pytest.raises(RuntimeError,match='primary'):await run(C(),Feed(),Feed(),tmp_path/'report',owner,shutdown_timeout=.2)
            assert owner.accepted and l.stop and any('FINAL' in e for e in owner.errors)
        finally:l.journal.close()
    asyncio.run(case())

def test_book_initialization_and_latched_loss():
    from .adapters import BookAdapter
    async def case():
        class Stream:
            healthy=False
            def read(self):return {'available':self.healthy}
            async def run(self,*,rest_seed_coro=None):await asyncio.Event().wait()
        s=Stream();b=BookAdapter(s,market='m',tokens={'UP':'u','DOWN':'d'});events=[]
        task=asyncio.create_task(b.run(events.append,initial_timeout=.5))
        await asyncio.sleep(.03);assert events==[] and b.state=='INITIALIZING'
        s.healthy=True;await b.wait_ready(.2);assert b.state=='SYNCHRONIZED'
        s.healthy=False;await asyncio.sleep(.04);s.healthy=True;await asyncio.sleep(.03)
        assert b.state in ('RESYNCHRONIZING','SYNCHRONIZED') and 'WS_DISCONNECT' in events and 'WS_RECONNECTING' in events
        task.cancel();await asyncio.gather(task,return_exceptions=True)
    asyncio.run(case())

def test_double_cancel_stubborn_feed_pending_order_retains_owner(tmp_path):
    from .supervisor import run
    async def case():
        l=ledger(tmp_path);release=asyncio.Event();a=Authority();calls=[]
        class C:
            ledger=l;busy=False;v1={'pending':[],'errors':[]};comparisons=[];kill_path=tmp_path/'stop';arm=types.SimpleNamespace(started_monotonic=time.monotonic())
            def guard(self):pass
            async def on_btc(self,*a):pass
            def on_status(self,*a):pass
            async def monitor_account(self):await release.wait()
        class Feed:
            async def run(self,*a):
                while not release.is_set():
                    try:await release.wait()
                    except asyncio.CancelledError:continue
        class Channel:
            async def accept(self,req):
                calls.append(req)
                while not release.is_set():
                    try:await release.wait()
                    except asyncio.CancelledError:continue
                return a.seal(dict(**req,owner='owner',receipt_id=str(len(calls)),accepted_ms=1000))
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner',clock=lambda:1000),timeout=.05)
        c=C();order=asyncio.create_task(Feed().run());c.v1={'pending':[order],'errors':[]}
        task=asyncio.create_task(run(c,Feed(),Feed(),tmp_path/'r',owner,shutdown_timeout=.05))
        await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.01);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert owner.tasks and l.stop
        release.set();c.busy=False;c.v1['pending']=[]
        await asyncio.sleep(.3)
        if owner.tasks:await asyncio.wait(owner.tasks,timeout=1)
        assert owner.accepted
        l.journal.close()
    asyncio.run(case())

def test_aggregate_logs_idle_disk_fault_and_secrets(tmp_path,monkeypatch):
    from .live_logging import LiveLog
    faults=[];out=io.StringIO();log=LiveLog(tmp_path,'one',console=out,background=False,on_fault=faults.append)
    try:
        log.write({'password':'CANARY','access_token':'CANARY','token':'CANARY'})
        assert 'CANARY' not in out.getvalue()
        (tmp_path/'old.log').write_bytes(b'x'*200)
        log.max_bytes=100
        with pytest.raises(OSError):log.tick()
        assert faults and (tmp_path/'old.log').stat().st_size==200
    finally:log.close()
