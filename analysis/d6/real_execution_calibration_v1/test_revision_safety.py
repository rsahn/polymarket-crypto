import asyncio,copy,io,types
import pytest
from .core import digest,Journal
from .custody import CustodyOwner,ReceiptVerifier,CustodyStateStore
from .test_repairs import Authority,evidence
from .test_calibration import ledger,reserve,intent,fill,snapshot
from .schemas import integer,hash256,identifiers,authenticate

@pytest.mark.parametrize('phase',['accept','verify'])
@pytest.mark.parametrize('change',['fill','ack'])
def test_receipt_race_never_releases_new_exposure(tmp_path,phase,change):
    async def case():
        l=ledger(tmp_path);reserve(l)
        if change=='fill':intent(l)
        else:l.intent('entry','BUY','t','m','.5','50','25',{},1000)
        count=[0];mutated=[False];a=Authority()
        def mutate():
            if mutated[0]:return
            mutated[0]=True
            if change=='fill':fill(l,q='1')
            else:l.ack('entry',{'ok':True,'order_id':'entry-remote'},1000)
        class A:
            async def verify_durable(self,r):
                if phase=='verify':mutate()
                return a.verify(r)
        class Channel:
            async def accept(self,req):
                count[0]+=1
                if phase=='accept':mutate()
                return a.seal(dict(**req,owner='owner',receipt_id=str(count[0]),accepted_ms=1000,future_result_client_ids=['entry']))
        class C:
            ledger=l;busy=False;v1={'pending':[]}
            async def monitor_account(self):await asyncio.Event().wait()
        owner=CustodyOwner(Channel(),ReceiptVerifier(A(),'owner',clock=lambda:1000))
        try:
            await asyncio.wait_for(owner.retain(C()),1)
            assert count[0]==2 and 'STALE_EXPOSURE_RECEIPT' in owner.errors
            assert owner.accepted['experiment']['exposure_revision']==l.custody_snapshot()['exposure_revision']
        finally:l.journal.close()
    asyncio.run(case())

def test_monitor_journal_writes_do_not_change_exposure_revision(tmp_path):
    l=ledger(tmp_path)
    try:
        before=l.custody_snapshot();l.emit('ACCOUNT_OBSERVATION_DURING_ORDER',{})
        assert l.custody_snapshot()['exposure_revision']==before['exposure_revision']
    finally:l.journal.close()

def test_cancelled_owner_remains_unresolved_and_close_refused(tmp_path):
    async def case():
        l=ledger(tmp_path);a=Authority();store=Journal(tmp_path/'custody','custody')
        class Channel:
            async def accept(self,req):await asyncio.Event().wait()
        class C:
            ledger=l;busy=False;v1={'pending':[]}
            async def monitor_account(self):await asyncio.Event().wait()
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner'),state_store=CustodyStateStore(store))
        task=owner.retain(C());await asyncio.sleep(.02);task.cancel();task.cancel()
        await asyncio.gather(task,return_exceptions=True);await asyncio.sleep(0)
        assert owner.states['experiment']=='UNRESOLVED_FAILURE'
        with pytest.raises(RuntimeError):await owner.shutdown_flat()
        assert [r['payload']['state'] for r in Journal.read(store.path)]==['OWNED','UNRESOLVED_FAILURE']
        l.journal.close();store.close()
    asyncio.run(case())

@pytest.mark.parametrize('fn,value',[(integer,True),(integer,-1),(hash256,'z'*64),(identifiers,'ab'),(identifiers,['a','a'])])
def test_strict_scalars(fn,value):
    with pytest.raises(ValueError):fn(value)

def test_coroutine_authority_is_never_truthy_proof():
    class A:
        async def verify(self,row):return True
    with pytest.raises(ValueError,match='SYNC'):authenticate(A(),{})

def test_raw_trade_normalizer_requires_final_effect_and_exact_intent():
    from .raw_trades import normalize_trade
    a=Authority();raw=dict(id='trade',market='m',asset_id='t',side='BUY',trader_side='TAKER',taker_order_id='o',maker_orders=[],price='.5',size='2',status='CONFIRMED')
    intent_row=dict(order_id='o',market='m',token='t',side='BUY')
    effect=dict(raw_digest=digest(raw),account='a',session='s',order_id='o',trade_id='trade',finality='FINAL',cash_effect_proven=True,share_effect_proven=True,cash_fee='.1',share_fee='.2',exchange_ts_ms=999)
    a.seal(effect)
    assert normalize_trade(raw,intent_row,effect,a,account='a',session='s',receive_ms=1000)['shares']=='2'
    for change in (dict(finality='PENDING'),dict(cash_effect_proven=False),dict(order_id='other')):
        bad=a.seal({**effect,**change})
        with pytest.raises(ValueError):normalize_trade(raw,intent_row,bad,a,account='a',session='s',receive_ms=1000)

def test_exclusive_logger_and_both_sink_redaction(tmp_path):
    from .live_logging import LiveLog,LoggedJournal
    log=LiveLog(tmp_path,'a',background=False,console=io.StringIO());j=LoggedJournal(tmp_path/'j','a',log)
    try:
        with pytest.raises(OSError):LiveLog(tmp_path,'b',background=False)
        j.append('STOP',{'nested':{'password':'CANARY','access_token':'CANARY'}})
        assert 'CANARY' not in j.path.read_text()+log.path.read_text()+log.console.getvalue()
    finally:j.close();log.close()

def test_fee_expiry_gates_new_reservation_not_late_accounting(tmp_path):
    from .qualification import FeeRisk
    risk=FeeRisk('1','1','1','a'*64,'m',1000)
    with pytest.raises(ValueError):risk.conservative_cash(1001)
    assert risk.observed_cash('.1','.2',2000)==__import__('decimal').Decimal('.3')

def test_partial_buy_sell_with_share_fee_preserves_nonnegative_position(tmp_path):
    from .qualification import FeeRisk
    l=ledger(tmp_path);l.seal_shadow('op',{'market':'m','token':'t'})
    risk=FeeRisk('1','1','1','a'*64,'m',1000);l.reserve('op','25','2',fee_risk=risk);intent(l)
    try:
        assert fill(l,q='10',sf='.2');l.terminal('entry','CANCELED','10');assert l.reconcile(snapshot(l),1000)
        # 9.8 held, remaining fee reserve .8 => sell at most 9.
        intent(l,'SELL','exit','9')
        assert fill(l,'exit','SELL','4','.49',sf='.3',trade='sell1')
        assert fill(l,'exit','SELL','5','.49',sf='.5',trade='sell2')
        assert l.positions['t']==0 and l.share_fees==1
    finally:l.journal.close()

def test_book_initial_timeout_never_becomes_ready():
    from .adapters import BookAdapter
    async def case():
        class S:
            def read(self):return {'available':False}
            async def run(self):await asyncio.Event().wait()
        b=BookAdapter(S(),market='m',tokens={'UP':'u','DOWN':'d'})
        with pytest.raises(TimeoutError):await b.run(lambda x:None,initial_timeout=.01)
        assert not b.ready.is_set() and b.state=='DEGRADED'
        await b.shutdown()
    asyncio.run(case())

@pytest.mark.parametrize('field',['account','market','session','tokens','owner','baseline','budget','client'])
def test_assembly_rejects_foreign_or_zero_budget_before_confirm(tmp_path,field):
    from .runner import PreparedSession
    a,v,e=evidence();a.client=object();base={'fixture':'baseline'}
    e['account_evidence_adapter_qualified']['payload']['baseline_digest']=digest(base)
    e['exit_handoff_ready']['payload']['owner']='owner'
    s=PreparedSession(directory=tmp_path,experiment_id='experiment',account='account',starting_cash='100',account_reader=None,position_reader=None,stream=object(),market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:1000,collateral='pUSD',baseline=base)
    owner=CustodyOwner(None,ReceiptVerifier(a,'owner'));client=a.client
    if field in ('account','market','session'):
        from .qualification import EvidenceVerifier
        context=dict(v.context);context[field]='other';v=EvidenceVerifier(a,**context)
    if field=='tokens':e['market_identity_verified']['payload']['outcome_tokens']={'UP':'d','DOWN':'u'}
    if field=='owner':owner.verifier.owner='other'
    if field=='baseline':e['account_evidence_adapter_qualified']['payload']['baseline_digest']='c'*64
    if field=='budget':e['balance_sufficient']['payload']['required_cash']='0'
    if field=='client':client=object()
    try:
        with pytest.raises(ValueError):s.validate_assembly(v,e,client,owner)
    finally:s.close()

def test_root_waits_after_exception_until_custody_transfer(tmp_path):
    from .runner import PreparedSession
    async def case():
        a,v,e=evidence();a.client=object();base={'fixture':'baseline'}
        e['account_evidence_adapter_qualified']['payload']['baseline_digest']=digest(base)
        e['exit_handoff_ready']['payload']['owner']='owner'
        for k in ('account_evidence_adapter_qualified','exit_handoff_ready'):
            e[k]['source_digest']=digest(e[k]['payload']);a.seal(e[k])
        release=asyncio.Event()
        class S:
            def read(self):return {'available':True}
            async def run(self):await asyncio.Event().wait()
        class Channel:
            async def accept(self,r):
                await release.wait();return a.seal(dict(**r,owner='owner',receipt_id='r',accepted_ms=1000))
        class Signal:
            async def run(self,*args):raise RuntimeError('PRIMARY')
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner',clock=lambda:1000),timeout=2)
        s=PreparedSession(directory=tmp_path,experiment_id='experiment',account='account',starting_cash='100',account_reader=None,position_reader=None,stream=S(),market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:1000,collateral='pUSD',baseline=base)
        arm=types.SimpleNamespace(nonce='fixture',started_monotonic=__import__('time').monotonic(),check=lambda *a:None)
        task=asyncio.create_task(s.start(client=a.client,verifier=v,evidence=lambda:e,signal_source=Signal(),custody_owner=owner,confirm=lambda *a,**k:arm))
        await asyncio.sleep(.3);assert not task.done()
        previous=owner.workers['experiment'];previous.cancel();previous.cancel()
        await asyncio.sleep(.3)
        assert not task.done() and not owner.monitors['experiment'].done()
        with pytest.raises(RuntimeError):s.close()
        release.set()
        with pytest.raises(RuntimeError,match='PRIMARY'):await task
        assert owner.states['experiment']=='TRANSFERRED'
        frozen=s.coordinator.fee_ceiling()
        s.coordinator.clock=lambda:2500
        fee=e['fee_upper_bound_proven'];fee['observed_ms']=2500;fee['valid_until_ms']=3500
        fee['payload']['epoch']='new-epoch';fee['payload']['cash_collateral']='2'
        fee['source_digest']=digest(fee['payload']);a.seal(fee)
        refreshed=s.coordinator.fee_ceiling()
        assert refreshed.epoch=='new-epoch' and refreshed.conservative_cash(2500)==3
        assert frozen.epoch=='fixture' and frozen.observed_cash('.1','.1',2500)>0
        s.close()
    asyncio.run(case())

def test_verifier_ignoring_cancel_has_single_tracked_operation(tmp_path):
    async def case():
        l=ledger(tmp_path);release=asyncio.Event();a=Authority();calls=[]
        class A:
            async def verify_durable(self,r):
                calls.append(r)
                while not release.is_set():
                    try:await release.wait()
                    except asyncio.CancelledError:continue
                return a.verify(r)
        class Channel:
            n=0
            async def accept(self,r):
                self.n+=1;return a.seal(dict(**r,owner='owner',receipt_id=str(self.n),accepted_ms=1000))
        class C:
            ledger=l;busy=False;v1={'pending':[]}
            async def monitor_account(self):await asyncio.Event().wait()
        owner=CustodyOwner(Channel(),ReceiptVerifier(A(),'owner',clock=lambda:1000),timeout=.01)
        task=owner.retain(C());await asyncio.sleep(.1)
        assert len(calls)==1 and len(owner.operations)==1
        release.set();await asyncio.wait_for(task,1);await owner.wait_resolved();l.journal.close()
    asyncio.run(case())

def test_production_root_refuses_wrong_volume_before_stream(tmp_path):
    from .runner import PreparedSession
    class Stream:
        async def run(self):raise AssertionError('must not start')
    a=Authority();owner=CustodyOwner(None,ReceiptVerifier(a,'owner'))
    s=PreparedSession(directory=tmp_path,experiment_id='experiment',account='account',starting_cash='100',account_reader=None,position_reader=None,stream=Stream(),market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:1000)
    try:
        if tmp_path.resolve().drive.lower()!='d:':
            with pytest.raises(ValueError,match='TARGET'):asyncio.run(s.start(client=object(),verifier=object(),evidence=lambda:{},signal_source=object(),custody_owner=owner))
        assert s.coordinator.arm is None and not s.ledger.orders
    finally:s.close()

@pytest.mark.parametrize('role',['TAKER','MAKER'])
def test_raw_attribution_exact_local_order_and_ambiguous_rejected(role):
    from .raw_trades import normalize_trade
    a=Authority();maker=dict(order_id='o',asset_id='t',maker_address='a',side='BUY',price='.5',matched_amount='2')
    raw=dict(id='trade',market='m',asset_id='t',side='BUY',trader_side=role,taker_order_id='o' if role=='TAKER' else 'other',maker_orders=[] if role=='TAKER' else [maker],price='.5',size='2',status='CONFIRMED')
    intent_row=dict(order_id='o',market='m',token='t',side='BUY')
    def effect(r):return a.seal(dict(raw_digest=digest(r),account='a',session='s',order_id='o',trade_id='trade',finality='FINAL',cash_effect_proven=True,share_effect_proven=True,cash_fee='0',share_fee='0',exchange_ts_ms=999))
    assert normalize_trade(raw,intent_row,effect(raw),a,account='a',session='s',receive_ms=1000)['shares']=='2'
    raw['maker_orders']=[maker,maker]
    with pytest.raises(ValueError):normalize_trade(raw,intent_row,effect(raw),a,account='a',session='s',receive_ms=1000)

def test_exit_requires_fresh_compatible_epoch_but_late_fill_uses_frozen_bound():
    from .qualification import FeeRisk
    old=FeeRisk('1','1','1','a'*64,'m',1000,'epoch1')
    with pytest.raises(ValueError):old.validate_exit_policy(old,1500)
    renewed=FeeRisk('1','1','1','a'*64,'m',2000,'epoch1')
    old.validate_exit_policy(renewed,1500)
    for candidate in (FeeRisk('1','1','1','a'*64,'m',2000,'epoch2'),FeeRisk('2','1','1','a'*64,'m',2000,'epoch1')):
        with pytest.raises(ValueError):old.validate_exit_policy(candidate,1500)
    assert old.observed_cash('.1','.2',5000)>0
