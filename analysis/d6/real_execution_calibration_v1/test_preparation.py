import asyncio,copy,io,types,time
import pytest
from .adapters import AccountAdapter,BookAdapter
from .qualification import FeeRisk,inspect_evidence
from .preflight import evaluate,REQUIRED
from .core import digest
from .live_logging import LiveLog,LoggedJournal
from .runner import DisabledPort,PreparedSession

class Reader:
    def __init__(self,row):self.row=row
    async def read(self):return copy.deepcopy(self.row)
    async def order(self,order_id):return {'available':True,'order':{'id':order_id}}

def test_account_does_not_promote_completeness():
    a=Reader(dict(available=True,wallet='a',collateral_symbol='pUSD',observed_ms=1000,balance_collateral='10',open_order_ids=[],trade_ids=['foreign'],complete=True,pagination_complete=True))
    p=Reader(dict(available=True,wallet='a',collateral_symbol='pUSD',observed_ms=1000,balances={},complete=True))
    adapter=AccountAdapter(a,p,account='a',collateral='pUSD',clock=lambda:1000)
    s=asyncio.run(adapter.snapshot())
    assert s['trade_ids']==['foreign'] and not s['inventory_proven'] and not s['orders_complete']
    with pytest.raises(ValueError,match='UNQUALIFIED'):asyncio.run(adapter.execution('id'))

def test_booleans_and_self_attested_envelopes_cannot_arm():
    r=evaluate({**dict.fromkeys(REQUIRED,True),'observed_ms':1000},1000,2**40)
    assert r['status']=='CALIBRATION_BLOCKED'
    e=dict(source='fixture',scope='fixture',source_digest=digest({}),payload={},observed_ms=1000,valid_until_ms=2000,strategy_hashes=r['strategy_hashes'])
    assert inspect_evidence(e,1000,r['strategy_hashes'])=='INDEPENDENT_VERIFIER_REQUIRED'

def test_fee_units_require_explicit_conversion_and_proof():
    f=FeeRisk('1','2',None,'a'*64,'m',2000)
    with pytest.raises(ValueError,match='UNITS'):f.conservative_cash(1000)
    f=FeeRisk('1','2','.5','a'*64,'m',2000)
    assert f.conservative_cash(1000)==2

def test_book_real_stream_causal_per_token():
    from backend.app.live.readonly_book_stream import StreamBook
    s=StreamBook('slug','m',['u','d'],10000,clock=lambda:1000);s.connected_generation()
    for token,stamp,receive in [('u',990,992),('d',995,998)]:
        s.ingest(dict(market='m',event_type='book',timestamp=str(stamp),asset_id=token,
          bids=[dict(price='.4',size='2')],asks=[dict(price='.6',size='3')]),wire_received_ms=receive)
    b=BookAdapter(s,market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:1000)
    up=asyncio.run(b.current('UP'));down=asyncio.run(b.current('DOWN'))
    assert up['receive_ms']==992 and down['receive_ms']==998
    assert up['book_state_id']!=down['book_state_id'] and up['valid']
    up['asks'].clear();assert asyncio.run(b.current('UP'))['asks']
    s.disconnect()
    with pytest.raises(ValueError):asyncio.run(b.current('UP'))

def test_live_log_rotation_redaction_quota(tmp_path):
    now=[0];out=io.StringIO();log=LiveLog(tmp_path,'fixture',background=False,clock=lambda:now[0],console=out,max_bytes=4096)
    j=LoggedJournal(tmp_path/'j','fixture',log)
    try:
        j.append('ARM_STATE',{'secret':'CANARY'});now[0]=18000;log.tick()
        j.append('EXPOSURE_CUSTODY_HANDOFF',{'acknowledged':False})
        assert log.part==1 and 'CANARY' not in out.getvalue() and 'SIMULATION_ONLY' not in out.getvalue()
        log.max_bytes=0
        with pytest.raises(OSError):j.append('STOP',{})
        assert j.failed
    finally:j.close();log.close()

def test_prepared_session_never_constructs_money_port(tmp_path):
    s=PreparedSession(directory=tmp_path,experiment_id='fixture',account='a',starting_cash='100',
      account_reader=object(),position_reader=object(),stream=object(),market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:1000)
    try:
        assert s.coordinator.arm is None and isinstance(s.coordinator.port,DisabledPort)
        with pytest.raises(ValueError):asyncio.run(s.start())
        with pytest.raises(ValueError):asyncio.run(s.coordinator.port.prepare())
    finally:s.close()

def test_exception_requires_durable_custody_before_monitor_cancel(tmp_path):
    from .test_calibration import ledger,reserve,intent,fill
    from .supervisor import run
    l=ledger(tmp_path);reserve(l);intent(l);fill(l)
    events=[]
    class C:
        ledger=l;v1={'errors':[],'pending':[]};arm=types.SimpleNamespace(started_monotonic=time.monotonic())
        kill_path=tmp_path/'kill';busy=False;comparisons=[]
        def guard(self):pass
        async def on_btc(self,*a):pass
        def on_status(self,*a):pass
        async def monitor_account(self):
            try:await asyncio.Event().wait()
            finally:events.append('monitor_cancel')
    class Feed:
        async def run(self,*a):raise RuntimeError('fixture_feed_failure')
    from .custody import CustodyOwner,ReceiptVerifier
    class Channel:
        async def accept(self,request):
            events.append('receipt');return dict(**request,owner='operator',receipt_id='one',accepted_ms=1000,future_result_client_ids=list(request['exposure']['orders']))
    class Authority:
        async def verify_durable(self,r):return True
    handoff=CustodyOwner(Channel(),ReceiptVerifier(Authority(),'operator',clock=lambda:1000))
    try:
        with pytest.raises(RuntimeError):asyncio.run(asyncio.wait_for(run(C(),Feed(),Feed(),tmp_path/'reports',handoff),3))
        assert 'receipt' in events and handoff.accepted
        assert any(r['kind']=='EXPOSURE_CUSTODY_HANDOFF' for r in l.journal.read(l.journal.path))
    finally:l.journal.close()
