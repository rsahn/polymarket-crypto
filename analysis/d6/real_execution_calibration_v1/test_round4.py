import asyncio,io,types
from dataclasses import replace
from decimal import Decimal
import pytest
from .test_calibration import ledger,signed
from .qualification import FeeRisk
from .engine import Coordinator
from .custody import CustodyOwner,ReceiptVerifier
from .test_repairs import Authority

@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('change',['cash','shares','epoch','expiry'])
def test_fee_changed_while_prepare_never_posts(tmp_path,side,change):
    async def case():
        l=ledger(tmp_path);risk=FeeRisk('1','0','1','a'*64,'m',2000,'epoch')
        l.seal_shadow('op',{'market':'m','token':'t'});l.reserve('op','25','1',fee_risk=risk)
        if side=='SELL':l.positions['t']=Decimal(50)
        policy=[risk];calls=[]
        class Port:
            maker='account';signer='signer'
            async def prepare(self,**kw):
                await asyncio.sleep(0)
                policy[0]=replace(risk,**{'cash':{'cash_collateral':'2'},'shares':{'outcome_shares':'1'},'epoch':{'epoch':'other'},'expiry':{'valid_until_ms':999}}[change])
                return signed(side=side,maker_amount=25000000 if side=='BUY' else 50000000,taker_amount=50000000 if side=='BUY' else 25000000)
            async def submit_once(self,*a):calls.append(a);raise AssertionError('POST')
        arm=types.SimpleNamespace(nonce='fixture',check=lambda *a:None)
        c=Coordinator(l,Port(),None,None,tmp_path/'STOP',arm=arm,fee_ceiling=lambda:policy[0],clock=lambda:1000)
        b=dict(valid=True,ws_healthy=True,market='m',token='t',book_state_id='state',source_ms=999,receive_ms=1000,asks=[['.5','100']],bids=[['.49','100']])
        try:
            with pytest.raises(ValueError,match='FEE'):await c.send('entry',side,b,Decimal(25) if side=='BUY' else Decimal(0),Decimal('.5'),Decimal(50))
            assert not calls and l.trades['op']['fee_risk']==risk
        finally:l.journal.close()
    asyncio.run(case())

def test_root_reclaims_cancelled_custody_worker_and_monitor(tmp_path):
    async def case():
        l=ledger(tmp_path);a=Authority();release=asyncio.Event();started=asyncio.Event();alive=[0]
        class Channel:
            n=0
            async def accept(self,r):
                self.n+=1;await release.wait()
                return a.seal(dict(**r,owner='owner',receipt_id=str(self.n),accepted_ms=1000))
        class C:
            ledger=l;busy=False;v1={'pending':[]}
            async def monitor_account(self):
                alive[0]+=1;started.set()
                try:await asyncio.Event().wait()
                finally:alive[0]-=1
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner',clock=lambda:1000),timeout=1)
        worker=owner.retain(C());root=asyncio.create_task(owner.wait_resolved())
        await started.wait();worker.cancel();worker.cancel();await asyncio.sleep(.25)
        assert not root.done() and alive[0]==1 and owner.workers['experiment'] is not worker
        release.set();await asyncio.wait_for(root,2);await asyncio.sleep(0)
        assert owner.states['experiment']=='TRANSFERRED';l.journal.close()
    asyncio.run(case())

@pytest.mark.parametrize('kind',['fork','older','no_lineage','valid'])
def test_authenticated_frontier_lineage(kind):
    from .adapters import AccountAdapter
    old={'sequence':2,'digest':'a'*64}
    new={'sequence':3,'digest':'b'*64};obs={'atomic_frontier':new,'ancestor_frontiers':[old]}
    if kind=='fork':obs['atomic_frontier']={'sequence':2,'digest':'c'*64}
    if kind=='older':obs['atomic_frontier']={'sequence':1,'digest':'a'*64}
    if kind=='no_lineage':obs['ancestor_frontiers']=[]
    if kind=='valid':AccountAdapter.check_lineage(old,obs)
    else:
        with pytest.raises(ValueError):AccountAdapter.check_lineage(old,obs)

def test_retained_nested_fields_never_leak_unapproved_token(tmp_path):
    from .live_logging import LiveLog,LoggedJournal
    log=LiveLog(tmp_path,'fixture',background=False,console=io.StringIO());log.public_tokens.add('public-outcome')
    journal=LoggedJournal(tmp_path/'ledger','fixture',log)
    try:
        journal.append('RECONCILIATION_OBSERVATION',{'snapshot':{'account':'a','cash':'1','token':'CANARY1','extra':{'token':'CANARY2'},'positions':{'public-outcome':'1'}},'decision_ms':1000})
        journal.append('FILL_OBSERVATION',{'client_id':'i','fill':{'trade_id':'trade','token':'public-outcome','shares':'1','extra':{'token':'CANARY3'},'fee_evidence':{'cash_effect_proven':True,'token':'CANARY4'}}})
        from .core import CalibrationLedger
        CalibrationLedger(journal,'a','1').seal_shadow('op',{'token':'CANARY5','expected_quantity':'1','actual_selected_book':{'token':'public-outcome','asks':[['.5','2']],'extra':{'token':'CANARY6'}}})
        value=journal.path.read_text()+log.path.read_text()+log.console.getvalue()
        assert 'CANARY' not in value and 'public-outcome' in journal.path.read_text() and 'cash_effect_proven' in value
    finally:journal.close();log.close()

@pytest.mark.parametrize('changed',['channel','custody_authority','account_source','account_authority','ws_tokens'])
def test_same_name_provider_replacement_rejected(tmp_path,changed):
    from .test_repairs import evidence
    from .runner import PreparedSession
    from .core import digest
    a,v,e=evidence();a.client=object();base={'fixture':'baseline'}
    e['account_evidence_adapter_qualified']['payload']['baseline_digest']=digest(base)
    e['exit_handoff_ready']['payload']['owner']='owner'
    source=object();channel=object()
    session=PreparedSession(directory=tmp_path,experiment_id='experiment',account='account',starting_cash='100',account_reader=None,position_reader=None,stream=object(),market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:1000,collateral='pUSD',baseline=base,evidence_source=source,authority=a)
    owner=CustodyOwner(channel,ReceiptVerifier(a,'owner'))
    try:
        session.validate_assembly(v,e,a.client,owner)
        if changed=='channel':owner.channel=object()
        if changed=='custody_authority':owner.verifier.authority=Authority()
        if changed=='account_source':session.account.evidence_source=object()
        if changed=='account_authority':session.account.authority=Authority()
        if changed=='ws_tokens':e['ws_healthy']['payload']['tokens']=['foreign','tokens']
        with pytest.raises(ValueError):session.validate_assembly(v,e,a.client,owner)
        assert session.coordinator.arm is None and not session.ledger.orders
    finally:session.close()
