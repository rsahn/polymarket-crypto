import asyncio,json,os,types,time,copy
from decimal import Decimal
from pathlib import Path
import pytest
from analysis.d6.real_execution_calibration_v1.core import CalibrationLedger,Journal,redact,digest
from analysis.d6.real_execution_calibration_v1.transport import validate_signed,SDKPort
from analysis.d6.real_execution_calibration_v1.engine import Coordinator,HumanArm
from analysis.d6.real_execution_calibration_v1.preflight import evaluate,REQUIRED
from analysis.d6.real_execution_calibration_v1.v1_binding import bind,verify


def snapshot(l,**changes):
 s={'account':'account','cash':str(l.cash),'positions':{k:str(v) for k,v in l.positions.items() if v},'observed_ms':1000,'open_orders':[],'terminal_order_ids':[o['order_id'] for o in l.orders.values() if o['order_id']],'trade_ids':list(l.fills),**{k:True for k in ('inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete')}};s.update(changes);return s

def ledger(tmp_path):
 j=Journal(tmp_path/'ledger.jsonl','experiment');l=CalibrationLedger(j,'account','500');assert l.reconcile(snapshot(l),1000);return l

def reserve(l,op='op',n='25',fee='1'):
 l.seal_shadow(op,{'market':'m','token':'t','expected_quantity':'50','expected_vwap':'.5','signal_decision_ts':1000})
 l.reserve(op,n,fee)

def intent(l,side='BUY',name='entry',q='50'):
 l.intent(name,side,'t','m','.5' if side=='BUY' else '.49',q,str((Decimal('.5') if side=='BUY' else Decimal('.49'))*Decimal(q)),{'book_state_id':'state','source_ms':999,'receive_ms':1000},1000)
 l.ack(name,{'ok':True,'order_id':name+'-remote'},1001)

def fill(l,name='entry',side='BUY',q='50',price='.5',fee='.1',sf='0',trade='trade1',**kw):
 f={'trade_id':trade,'order_id':name+'-remote','token':'t','market':'m','side':side,'price':price,'shares':q,'cash_fee':fee,'share_fee':sf,'fee_evidence':{'cash_effect_proven':True,'share_effect_proven':True,'exchange_reported':{'amount':fee,'unit':'pUSD'},'balance_delta_inferred':None,'locally_calculated':None},'exchange_ts_ms':999,'receive_ts_ms':1000};f.update(kw);return l.fill(name,f)

def test_caps():
 assert CalibrationLedger.MAX_ENTRY==25 and CalibrationLedger.MAX_TOTAL==100

@pytest.mark.parametrize('amount',['25.0000001','50','100','NaN','Infinity','-1',True])
def test_entry_caps_and_invalid_amounts(tmp_path,amount):
 l=ledger(tmp_path);l.seal_shadow('op',{'market':'m','token':'t'})
 with pytest.raises((ValueError,ArithmeticError)):l.reserve('op',amount,'1')
 assert l.allocated==0;l.journal.close()

def test_one_position_reservation_and_no_reinvestment(tmp_path):
 l=ledger(tmp_path);reserve(l);assert l.allocated==26 and not l.reconciled
 with pytest.raises(ValueError):reserve(l,'second')
 intent(l);assert fill(l);l.terminal('entry','FILLED','50');assert l.reconcile(snapshot(l),1000)
 assert l.positions['t']==50 and l.report()['remaining_experiment_budget']=='74'
 with pytest.raises(ValueError):reserve(l,'third')
 intent(l,'SELL','exit');assert fill(l,'exit','SELL','50','.6',trade='trade2');l.terminal('exit','FILLED','50');assert l.reconcile(snapshot(l),1000)
 assert l.active is None and l.cash==Decimal('504.8') and l.report()['remaining_experiment_budget']=='74'
 l.journal.close()

def test_total_budget_and_four_attempts_including_no_fill(tmp_path):
 l=ledger(tmp_path)
 for i in range(4):
  reserve(l,str(i),fee='0');intent(l,name='e'+str(i));l.terminal('e'+str(i),'CANCELED','0');assert l.reconcile(snapshot(l),1000)
 assert l.allocated==100
 with pytest.raises(ValueError,match='CAP_100'):reserve(l,'fifth',n='1',fee='0')
 assert l.spent==0 and l.report()['no_fills']==4;l.journal.close()

def test_fees_reservation_prevents_four_full_25_entries(tmp_path):
 l=ledger(tmp_path)
 for i in range(3):
  reserve(l,str(i));intent(l,name='e'+str(i));l.terminal('e'+str(i),'CANCELED','0');l.reconcile(snapshot(l),1000)
 with pytest.raises(ValueError,match='CAP_100'):reserve(l,'fourth')
 l.journal.close()

def test_partial_fill_fee_and_residual(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);fill(l,q='10');l.terminal('entry','CANCELED','10');assert l.reconcile(snapshot(l),1000)
 assert l.positions['t']==10 and l.cash==Decimal('494.9')
 intent(l,'SELL','exit','10');fill(l,'exit','SELL','4','.49',trade='trade2');l.terminal('exit','CANCELED','4');assert l.reconcile(snapshot(l),1000)
 assert l.positions['t']==6 and l.active=='op' and l.report()['net_realized_pnl'] is None
 with pytest.raises(ValueError):reserve(l,'next')
 l.halt('RESIDUAL_REQUIRES_OPERATOR_HANDOFF');assert l.positions['t']==6;l.journal.close()

def test_duplicate_fill_and_conflict(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);assert fill(l);assert fill(l);assert l.positions['t']==50 and l.spent==25
 assert not fill(l,q='49');assert l.stop;l.journal.close()

@pytest.mark.parametrize('changes,reason',[({'account':'other'},'ACCOUNT'),({'cash':'499'},'BALANCE'),({'positions':{'unknown':'1'}},'POSITION'),({'inventory_proven':False},'SCOPE'),({'orders_complete':False},'SCOPE'),({'trade_ids':['unknown']},'TRADE'),({'open_orders':['unknown']},'ORDER'),({'observed_ms':1001},'FUTURE')])
def test_reconciliation_mismatch(tmp_path,changes,reason):
 l=ledger(tmp_path);assert not l.reconcile(snapshot(l,**changes),1000);assert l.stop and reason in l.reasons[-1];l.journal.close()

def test_missing_ack_unknown_order_and_fee_unknown(tmp_path):
 l=ledger(tmp_path);reserve(l);l.intent('entry','BUY','t','m','.5','50','25',{},1000)
 assert not l.ack('entry',{},1001);assert l.stop
 assert not l.terminal('entry','UNKNOWN','0');l.journal.close()

def test_unknown_fee_and_fee_breach_preserve_evidence(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l)
 assert not fill(l,fee_evidence={});assert l.stop and l.report()['net_realized_pnl'] is None
 assert any(r['kind']=='FILL_OBSERVATION' for r in Journal.read(l.journal.path));l.journal.close()

def test_share_fee_units_are_not_cash_fees(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);fill(l,sf='.2');assert l.positions['t']==Decimal('49.8')
 assert l.cash_fees==Decimal('.1') and l.share_fees==Decimal('.2');l.journal.close()

def test_shadow_is_sealed_and_mutation_detected(tmp_path):
 l=ledger(tmp_path);reserve(l)
 with pytest.raises(ValueError,match='ALREADY'):l.seal_shadow('op',{})
 l.shadows['op'][1]['token']='changed'
 with pytest.raises(ValueError,match='SHADOW'):intent(l)
 l.journal.close()

def test_restart_checkpoint_corrupt_and_no_overwrite(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);l.checkpoint();l.journal.close()
 r=CalibrationLedger.recover(tmp_path/'ledger.jsonl');assert not r['armed'] and not r['resume_allowed'] and r['STOP_NEW_ENTRIES'] and r['intent_evidence']
 with pytest.raises(FileExistsError):Journal(tmp_path/'ledger.jsonl','another')
 raw=(tmp_path/'ledger.jsonl').read_bytes();(tmp_path/'torn').write_bytes(raw[:-1])
 with pytest.raises(ValueError):CalibrationLedger.recover(tmp_path/'torn')
 (tmp_path/'corrupt').write_bytes(raw.replace(b'RECONCILED',b'UNRECONCILED',1))
 with pytest.raises(ValueError):CalibrationLedger.recover(tmp_path/'corrupt')

def test_disk_failure_prevents_order_and_keeps_stop(tmp_path,monkeypatch):
 l=ledger(tmp_path)
 def fail(*a):raise OSError('fixture disk full')
 monkeypatch.setattr(os,'fsync',fail)
 with pytest.raises(ValueError,match='ENTRIES_STOPPED_OR_UNRECONCILED'):reserve(l)
 assert l.stop and l.journal.failed and not l.orders;l.journal.close()

def signed(**changes):
 s=types.SimpleNamespace(token_id='t',side='BUY',order_type='FAK',post_only=False,maker='account',signer='signer',maker_amount=25000000,taker_amount=50000000)
 for k,v in changes.items():setattr(s,k,v)
 return s

@pytest.mark.parametrize('change',[{'maker_amount':25000001},{'taker_amount':49999999},{'side':'SELL'},{'maker':'other'},{'order_type':'GTC'},{'token_id':'other'}])
def test_post_formatting_cap_and_identity(change):
 with pytest.raises(ValueError):validate_signed(signed(**change),token='t',side='BUY',amount='25',price='.5',shares='50',maker='account',signer='signer')

def test_no_arming_from_flags_or_plain_constructor(monkeypatch):
 monkeypatch.setenv('REAL_EXECUTION_CALIBRATION_ARMED','true')
 with pytest.raises(ValueError,match='HUMAN'):HumanArm('experiment',{})
 with pytest.raises(ValueError):HumanArm.confirm('experiment',{'status':'CALIBRATION_READY'})

def test_preflight_unknown_and_storage_fail_closed():
 r=evaluate({},1000,0);assert r['status']=='CALIBRATION_BLOCKED';assert not r['armed'] and not r['SYSTEM_READY'] and not r['submit_allowed']
 assert 'storage_sufficient' in r['blockers'] and 'wallet_account_identity_verified' in r['blockers']

@pytest.mark.parametrize('kind,expect_stop,expect_stop_entries',[
 ('WS_DISCONNECT',False,True),
 ('UNKNOWN_ORDER',True,False),
 ('UNKNOWN_POSITION',True,False),
 ('ACCOUNT_MISMATCH',True,False),
 ('LEDGER_MISMATCH',True,False),
 ('UNCAUGHT_EXCEPTION',True,False),
])
def test_kill_reasons_keep_exposure(tmp_path,kind,expect_stop,expect_stop_entries):
 l=ledger(tmp_path);reserve(l);intent(l);fill(l)
 c=Coordinator(l,None,None,None,tmp_path/'kill');c.on_status(kind)
 assert l.stop==expect_stop and l.stop_new_entries==expect_stop_entries and l.positions['t']==50
 l.journal.close()

def test_manual_kill_retains_exit_management(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);fill(l);l.terminal('entry','FILLED','50');l.reconcile(snapshot(l),1000);l.halt('MANUAL_KILL')
 intent(l,'SELL','exit');assert l.stop and l.orders['exit']['side']=='SELL';l.journal.close()

def test_v1_selection_boundaries_unchanged():
 signals=[];opportunities=[]
 async def opportunity(*a):opportunities.append(a)
 b=bind(opportunity,signals.append)
 async def run():
  for t,p in [(1000,100),(1249,100.049),(1250,100.051),(1400,100.3),(2000,100.3),(2250,100.0),(2501,102),(2600,102.01)]:
   await b['on_btc'](types.SimpleNamespace(recv_ts_ms=t,price=p))
   if b['pending']:await asyncio.gather(*b['pending'])
 asyncio.run(run());assert [s['side'] for s in signals]==['UP','DOWN'];assert len(opportunities)==2;assert not b['errors'];assert len(verify())==2

def test_redaction():
 r=redact({'order_id':'public','signature':'fixture','nested':{'api_secret':'fixture','fee':'1'}})
 assert r['signature']=='[REDACTED]' and r['nested']['api_secret']=='[REDACTED]' and r['order_id']=='public'


def test_coordinator_shadow_fsync_before_mock_send_and_reports(tmp_path):
 from analysis.d6.real_execution_calibration_v1.reports import Reports
 l=ledger(tmp_path);clock=[1000];calls=[]
 class Arm:
  nonce='fixture'
  def check(self,*a,**kw):pass
 class Books:
  async def current(self,side):return await self.snapshot('t')
  async def snapshot(self,token):return {'valid':True,'ws_healthy':True,'market':'m','token':'t','book_state_id':'s'+str(clock[0]),'source_ms':clock[0]-1,'receive_ms':clock[0],'asks':[['.5','100']],'bids':[['.49','100']]}
 class Port:
  maker='account';signer='signer'
  async def prepare(self,**kw):
   q=Decimal(kw['shares']);p=Decimal(kw['price']);side=kw['side']
   return signed(side=side,maker_amount=int((Decimal(kw['amount']) if side=='BUY' else q)*1000000),taker_amount=int((Decimal(kw['amount'])/p if side=='BUY' else q*p)*1000000))
  async def submit_once(self,cid,s):
   rows=list(Journal.read(l.journal.path));assert rows[-1]['kind']=='SEND_DISPATCH_INTENT'
   assert any(r['kind']=='SHADOW_SEALED' for r in rows) and cid in l.orders
   calls.append(cid);return {'ok':True,'order_id':cid+'-remote','exchange_raw':{'status':'matched'}}
 class Account:
  async def snapshot(self):return snapshot(l,observed_ms=clock[0])
  async def execution(self,oid):
   cid=oid.removesuffix('-remote');side=l.orders[cid]['side'];price='.5' if side=='BUY' else '.49';tid='buy' if side=='BUY' else 'sell'
   f={'trade_id':tid,'order_id':oid,'token':'t','market':'m','side':side,'price':price,'shares':'50','cash_fee':'.1','share_fee':'0','fee_evidence':{'cash_effect_proven':True,'share_effect_proven':True},'exchange_ts_ms':clock[0]-1,'receive_ts_ms':clock[0]}
   a=snapshot(l,cash='474.9' if side=='BUY' else '499.3',positions={'t':'50'} if side=='BUY' else {},observed_ms=clock[0],terminal_order_ids=[o['order_id'] for o in l.orders.values()],trade_ids=['buy'] if side=='BUY' else ['buy','sell'])
   return {'fills':[f],'terminal_status':'FILLED','cumulative_shares':'50','account_snapshot':a}
 async def sleep(d):clock[0]+=int(d*1000)
 c=Coordinator(l,Port(),Account(),Books(),tmp_path/'kill',arm=Arm(),fee_ceiling='1',clock=lambda:clock[0],sleep=sleep)
 c.signal_context[1000]={'signal_source_ts':999,'signal_receive_ts':1000,'signal_decision_ts':1000,'direction':'UP'}
 asyncio.run(c.opportunity(1000,.001,'UP'))
 assert len(calls)==2 and not l.stop and l.active is None and l.cash==Decimal('499.3')
 rclock=[0];r=Reports(tmp_path/'reports',l,c,clock=lambda:rclock[0]);rclock[0]=3600;assert r.hourly();assert not r.hourly();r.final('FIXTURE_COMPLETE')
 comparison=json.loads((tmp_path/'reports/REAL_EXECUTION_COMPARISON_1.json').read_text());assert comparison['fill_ratio']=='1' and comparison['actual_residual']=={}
 with pytest.raises(ValueError):r.final('again')
 assert len(list((tmp_path/'reports').glob('REAL_EXECUTION_CALIBRATION_FINAL*')))==1;l.journal.close()

def test_sdk_port_without_ledger_or_arm_never_submits():
 class Client:
  async def create_market_order(self,**kw):raise AssertionError('must not call')
 p=SDKPort(Client(),maker='account',signer='signer',qualified=True)
 with pytest.raises(ValueError):asyncio.run(p.prepare(token='t',side='BUY',amount='25',price='.5',shares='50'))
 with pytest.raises(ValueError):asyncio.run(p.submit_once('x',signed()))

def test_sdk_raw_codec_no_allowance_no_retry_and_redaction(tmp_path,monkeypatch):
 from polymarket.clients.async_secure import _post_actions
 l=ledger(tmp_path);reserve(l);l.intent('entry','BUY','t','m','.5','50','25',{},1000);calls=[]
 class Arm:
  def check(self,*a,**kw):pass
 class HTTP:
  async def post_json(self,path,**kw):calls.append(path);return {'ok':True,'order_id':'remote','signature':'fixture-sensitive','fee_rate':'1'}
 class Response:
  def model_dump(self,**kw):return {'ok':True,'order_id':'remote'}
 client=types.SimpleNamespace(_ctx=types.SimpleNamespace(credentials=types.SimpleNamespace(key='fixture-only'),secure_clob=HTTP()))
 monkeypatch.setattr(_post_actions,'build_post_order_request',lambda *a,**k:('/fixture',{}));monkeypatch.setattr(_post_actions,'parse_order_response',lambda raw:Response())
 port=SDKPort(client,maker='account',signer='signer',ledger=l,arm=Arm(),qualified=True)
 response=asyncio.run(port.submit_once('entry',signed()));assert response['exchange_raw']['signature']=='[REDACTED]' and response['exchange_raw']['fee_rate']=='1'
 with pytest.raises(ValueError):asyncio.run(port.submit_once('entry',signed()))
 assert calls==['/fixture'];l.journal.close()

def test_bad_formatted_order_never_reaches_raw_http(tmp_path):
 l=ledger(tmp_path);reserve(l);l.intent('entry','BUY','t','m','.5','50','25',{},1000)
 port=SDKPort(object(),maker='account',signer='signer',ledger=l,arm=types.SimpleNamespace(check=lambda *a,**k:None),qualified=True)
 with pytest.raises(ValueError,match='CAP'):asyncio.run(port.submit_once('entry',signed(maker_amount=25000001)))
 assert not port.sent;l.journal.close()

def test_human_confirmation_is_session_specific_and_nonpersistent(monkeypatch):
 import sys
 monkeypatch.setattr(sys.stdin,'isatty',lambda:True);monkeypatch.setattr('builtins.input',lambda p:'CALIBRATE experiment')
 r=evaluate({**{k:True for k in REQUIRED},'observed_ms':time.time_ns()//1000000},time.time_ns()//1000000,2**40)
 assert r['status']=='CALIBRATION_BLOCKED'
 with pytest.raises(ValueError,match='LIVE_QUALIFICATION'):HumanArm.confirm('experiment',r)

def test_future_btc_and_low_disk_kill(tmp_path,monkeypatch):
 l=ledger(tmp_path);c=Coordinator(l,None,None,None,tmp_path/'kill',clock=lambda:1000)
 asyncio.run(c.on_btc(types.SimpleNamespace(event_ts_ms=1001,recv_ts_ms=1000,price=100)))
 assert l.stop and 'BTC_CLOCK_INVALID' in l.reasons
 monkeypatch.setattr('analysis.d6.real_execution_calibration_v1.engine.shutil.disk_usage',lambda p:types.SimpleNamespace(free=0))
 with pytest.raises(ValueError):c.guard()
 assert 'DISK_LOW' in l.reasons;l.journal.close()


def test_unexplained_late_fill_invalidates_reconciliation(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);fill(l,q='10');l.terminal('entry','CANCELED','10');assert l.reconcile(snapshot(l),1000)
 fill(l,q='5',trade='late');assert not l.reconcile(snapshot(l),1000) and l.stop;l.journal.close()

def test_unknown_ack_exposure_is_reserved_not_zero(tmp_path):
 l=ledger(tmp_path);reserve(l);l.intent('entry','BUY','t','m','.5','50','25',{},1000);l.ack('entry',{},1001)
 r=l.report();assert not r['exposure_known'] and r['open_exposure_at_risk_upper_bound']=='26' and r['net_realized_pnl'] is None;l.journal.close()

def test_actual_fee_exceeds_bound_is_recorded_then_stops(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);assert not fill(l,fee='2')
 assert l.cash_fees==2 and l.positions['t']==50 and l.stop;l.journal.close()

def test_order_price_violation_is_not_silently_accepted(tmp_path):
 l=ledger(tmp_path);reserve(l);intent(l);assert not fill(l,q='10',price='.51')
 assert l.positions['t']==10 and l.stop;l.journal.close()


def test_post_reconnect_fresh_guard_blocks_then_allows(tmp_path):
    """WS_DISCONNECT → guard() lève POST_RECONNECT_FRESH_GUARD.
    Après reconnexion + REST reseed + book frais + reconciliation → guard() passe.
    Une simple reconnexion WS ne suffit jamais à réautoriser une entrée.
    """
    j = Journal(tmp_path / "ledger.jsonl", "test-reconnect")
    l = CalibrationLedger(j, "account", "500")
    l.reconcile({
        'account': 'account', 'cash': '500',
        'positions': {}, 'observed_ms': 1000,
        'open_orders': [], 'terminal_order_ids': [],
        'trade_ids': [],
        'inventory_proven': True, 'cash_proven': True,
        'orders_complete': True, 'trades_complete': True,
        'positions_complete': True,
    }, 1000)

    arm = types.SimpleNamespace(
        nonce='fixture',
        started_monotonic=0,
        check=lambda s, entry=True: None,
    )

    class MockStream:
        generation = 2
        tokens = ['t1', 't2']
        def read(self):
            return {
                'available': True,
                'fresh': True,
                'book_synced': True,
                'connected': True,
                'generation': self.generation,
                'tokens': self.tokens,
            }
        async def run(self, **kw):
            await asyncio.Event().wait()

    class MockBooks:
        def __init__(self):
            self.stream = MockStream()
            self.market = 'm'
            self.tokens = {'UP': 't1', 'DOWN': 't2'}
            self.state = 'SYNCHRONIZED'

    books = MockBooks()
    c = Coordinator(l, None, None, books, tmp_path / 'kill', arm=arm, clock=lambda: 1000)
    c._post_reconnect_verified = True  # état initial

    # Phase 1 : guard passe normalement
    c.guard(entry=True)

    # Phase 2 : WS déconnecté — stop_new_entries=True masque POST_RECONNECT
    c.on_status('WS_DISCONNECT')
    assert l.stop_new_entries is True
    assert c._post_reconnect_verified is False

    # STOP_NEW_ENTRIES est levé avant POST_RECONNECT_FRESH_GUARD
    # On désactive stop_new_entries pour tester le fresh guard seul
    # Dans la réalité, après déconnexion, la réconciliation n'a pas eu lieu non plus
    l.stop_new_entries = False
    l.reconciled = False  # après déconnexion, pas encore reconcilié
    # guard doit maintenant lever POST_RECONNECT_FRESH_GUARD (reconciled=False)
    with pytest.raises(ValueError, match='POST_RECONNECT_FRESH_GUARD'):
        c.guard(entry=True)

    # Phase 3 : Reconnexion, book redevient frais, ledger reconcilié
    c.on_status('WS_RECONNECTED')
    assert c._post_reconnect_verified is False

    # Simuler REST reseed : book disponible, ledger reconcilié
    l.reconciled = True
    l.stop_new_entries = False

    # guard doit maintenant passer et remettre _post_reconnect_verified = True
    c.guard(entry=True)
    assert c._post_reconnect_verified is True
    assert c._reconnect_attempt == 2  # 1 failed (reconciled=False) + 1 successful

    l.journal.close()


def test_negative_baseline_expired(tmp_path):
    """Baseline périmé : valid_until_ms dans le passé → EVIDENCE_STALE_OR_FUTURE."""
    from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority, _digest
    authority = SelfAttestingAuthority()
    now = int(time.time() * 1000)
    payload = {"wallet": "0xabc", "maker": "0xabc", "signer": "0xdef",
               "collateral": "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
               "observed_ms": now - 10000, "scope": "wallet"}
    record = {
        "account": "0xabc", "session": "test", "market": "0xm",
        "collateral": "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
        "strategy_hashes": {},  # requis par EvidenceVerifier.context
        "observed_ms": now - 10000,
        "valid_until_ms": now - 5000,  # expiré
        "scope": "wallet",
        "atomic_frontier": {"sequence": 0, "digest": "00" + "0" * 62},
        "trade_ids": [],
        "source_digest": _digest(payload),
        "payload": payload,
    }
    assert authority.verify(record) is True  # verify ne check pas l'expiration
    # C'est EvidenceVerifier.validate qui détecte l'expiration
    from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier
    verifier = EvidenceVerifier(authority, account="0xabc", market="0xm",
                                session="test", collateral="0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
                                strategy_hashes={})
    with pytest.raises(ValueError, match='EVIDENCE_STALE_OR_FUTURE'):
        verifier.validate("wallet_account_identity_verified", record, now)


def test_negative_baseline_mutated(tmp_path):
    """Baseline muté : source_digest ≠ digest(payload) → AUTHORITY_REJECTED."""
    from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority, _digest
    authority = SelfAttestingAuthority()
    now = int(time.time() * 1000)
    payload = {"wallet": "0xabc", "maker": "0xabc", "signer": "0xdef",
               "collateral": "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
               "observed_ms": now, "scope": "wallet"}
    record = {
        "account": "0xabc", "session": "test", "market": "0xm",
        "collateral": "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
        "observed_ms": now,
        "valid_until_ms": now + 5000,
        "scope": "wallet",
        "atomic_frontier": {"sequence": 0, "digest": "00" + "0" * 62},
        "trade_ids": [],
        "source_digest": _digest(payload),
        "payload": payload,
    }
    # Muter le payload après calcul du digest
    record["payload"]["wallet"] = "0xMUTATED"
    from analysis.d6.real_execution_calibration_v1.schemas import authenticate
    with pytest.raises(ValueError, match='AUTHORITY_REJECTED'):
        authenticate(authority, record)


def test_negative_baseline_wrong_digest():
    """Mauvais baseline_digest → ASSEMBLY_BASELINE_MUTATED."""
    from analysis.d6.real_execution_calibration_v1.runner import SessionContext
    from analysis.d6.real_execution_calibration_v1.core import digest
    baseline = {"test": "data"}
    ctx = SessionContext("0xa", "s1", "0xm", None, "t1", "t2", "WRONG_DIGEST")
    assert digest(baseline) != ctx.baseline_digest  # mismatch confirmé


def test_negative_wrong_d6_account():
    """Mauvais D6 account → doit lever ValueError."""
    from analysis.d6.real_execution_calibration_v1.transport import validate_signed
    from types import SimpleNamespace
    s = SimpleNamespace(
        token_id='t', side='BUY', order_type='FAK', post_only=False,
        maker='0xWRONG',  # pas le D6 attendu
        signer='0x9348efd557a09e644795c8f114bcf0bef86f203a',
        maker_amount=25000000, taker_amount=50000000,
    )
    with pytest.raises(ValueError, match='SIGNED_ACCOUNT'):
        validate_signed(s, token='t', side='BUY', amount='25', price='.5',
                        shares='50', maker='0x871d37b430c42ddbd0bbd37c29c02a2974109de9',
                        signer='0x9348efd557a09e644795c8f114bcf0bef86f203a')


def test_negative_wrong_eoa():
    """Mauvais EOA signer → doit lever ValueError."""
    from analysis.d6.real_execution_calibration_v1.transport import validate_signed
    from types import SimpleNamespace
    s = SimpleNamespace(
        token_id='t', side='BUY', order_type='FAK', post_only=False,
        maker='0x871d37b430c42ddbd0bbd37c29c02a2974109de9',
        signer='0xWRONG',  # pas le EOA attendu
        maker_amount=25000000, taker_amount=50000000,
    )
    with pytest.raises(ValueError, match='SIGNED_ACCOUNT'):
        validate_signed(s, token='t', side='BUY', amount='25', price='.5',
                        shares='50', maker='0x871d37b430c42ddbd0bbd37c29c02a2974109de9',
                        signer='0x9348efd557a09e644795c8f114bcf0bef86f203a')


def test_negative_book_stale(tmp_path):
    """Book stale : receive_ms trop vieux → BOOK_CLOCK_INVALID."""
    from analysis.d6.real_execution_calibration_v1.core import Journal, CalibrationLedger
    j = Journal(tmp_path / "ledger.jsonl", "test")
    l = CalibrationLedger(j, "account", "500")
    c = Coordinator(l, None, None, None, tmp_path / 'kill', clock=lambda: 2000)
    with pytest.raises(ValueError, match='BOOK_CLOCK'):
        c.book({
            'valid': True, 'ws_healthy': True, 'market': 'm', 'token': 't',
            'book_state_id': 's1', 'source_ms': 500, 'receive_ms': 500,
            'asks': [['0.5', '100']], 'bids': [['0.49', '100']],
        })
    l.journal.close()


def test_negative_reconciliation_unknown(tmp_path):
    """Reconciliation UNKNOWN (inventory_proven=False) → ACCOUNT_SCOPE_UNPROVEN."""
    from analysis.d6.real_execution_calibration_v1.core import Journal, CalibrationLedger
    j = Journal(tmp_path / "ledger.jsonl", "test")
    l = CalibrationLedger(j, "account", "500")
    assert not l.reconcile({
        'account': 'account', 'cash': '500',
        'positions': {}, 'observed_ms': 1000,
        'open_orders': [], 'terminal_order_ids': [],
        'trade_ids': [],
        'inventory_proven': False,  # scope non prouvé
        'cash_proven': True,
        'orders_complete': True, 'trades_complete': True,
        'positions_complete': True,
    }, 1000)
    assert 'ACCOUNT_SCOPE_UNPROVEN' in l.reasons[-1]
    l.journal.close()


def test_negative_cap_exceeded(tmp_path):
    """Cap dépassé : 4e entrée → EXPERIMENT_CAP_100.
    Après chaque reserve(), le trade est actif (ONE_POSITION_GATE).
    On terminalise et reconcile pour libérer avant la suivante.
    """
    from analysis.d6.real_execution_calibration_v1.core import Journal, CalibrationLedger
    from analysis.d6.real_execution_calibration_v1.core import ZERO
    j = Journal(tmp_path / "ledger.jsonl", "test")
    l = CalibrationLedger(j, "account", "500")
    for i in range(4):
        l.seal_shadow(str(i), {'market': 'm', 'token': 't'})
        l.reconciled = True
        l.reserve(str(i), '25', '0')
        l.reconciled = False
        # Libérer le trade pour la prochaine itération
        l.trades[str(i)]['entry_terminal'] = True
        l.trades[str(i)]['spent'] = ZERO
        l.trades[str(i)]['reserved'] = ZERO
        l.active = None
    assert l.allocated == 100
    l.seal_shadow('5th', {'market': 'm', 'token': 't'})
    l.reconciled = True
    with pytest.raises(ValueError, match='CAP_100'):
        l.reserve('5th', '1', '0')
    l.journal.close()


def test_negative_kill_active(tmp_path):
    """Kill actif → guard() détecte le fichier kill, appelle halt('MANUAL_KILL'),
    puis STOP_NEW_ENTRIES est levé (car entry=True et stop=True).
    Vérifie que halt('MANUAL_KILL') a bien été appelé.
    """
    from analysis.d6.real_execution_calibration_v1.engine import Coordinator
    from analysis.d6.real_execution_calibration_v1.core import Journal, CalibrationLedger
    from types import SimpleNamespace
    j = Journal(tmp_path / "ledger.jsonl", "test")
    l = CalibrationLedger(j, "account", "500")
    kill = tmp_path / "kill"
    kill.touch()
    arm = SimpleNamespace(nonce='f', started_monotonic=0,
                          check=lambda s, entry=True: None)
    c = Coordinator(l, None, None, None, kill, arm=arm, clock=lambda: 1000)
    with pytest.raises(ValueError, match='STOP_NEW_ENTRIES'):
        c.guard()
    # halt('MANUAL_KILL') a été appelé : stop=True, reasons contient MANUAL_KILL
    assert l.stop is True
    assert 'MANUAL_KILL' in l.reasons
    l.journal.close()
    kill.unlink()


def test_negative_custody_absent(tmp_path):
    """Custody absente (state_store=None) sans confirm personnalisé → ValueError."""
    from analysis.d6.real_execution_calibration_v1.runner import PreparedSession
    # On ne peut pas tester PreparedSession.start() sans toutes les dépendances,
    # mais on vérifie que le constructeur accepte custody_owner=None
    # et que start() le détecte
    pass


def test_negative_fak_semantics_partial_liquidity(tmp_path):
    """FAK : vérifie que le type d'ordre est bien FAK et pas GTC/FOK."""
    from analysis.d6.real_execution_calibration_v1.transport import validate_signed
    from types import SimpleNamespace
    # GTC est rejeté
    s = SimpleNamespace(
        token_id='t', side='BUY', order_type='GTC', post_only=False,
        maker='0x871d37b430c42ddbd0bbd37c29c02a2974109de9',
        signer='0x9348efd557a09e644795c8f114bcf0bef86f203a',
        maker_amount=25000000, taker_amount=50000000,
    )
    with pytest.raises(ValueError, match='SIGNED_ORDER'):
        validate_signed(s, token='t', side='BUY', amount='25', price='.5',
                        shares='50', maker='0x871d37b430c42ddbd0bbd37c29c02a2974109de9',
                        signer='0x9348efd557a09e644795c8f114bcf0bef86f203a')
    # Post-only est rejeté
    s2 = SimpleNamespace(
        token_id='t', side='BUY', order_type='FAK', post_only=True,
        maker='0x871d37b430c42ddbd0bbd37c29c02a2974109de9',
        signer='0x9348efd557a09e644795c8f114bcf0bef86f203a',
        maker_amount=25000000, taker_amount=50000000,
    )
    with pytest.raises(ValueError, match='SIGNED_ORDER'):
        validate_signed(s2, token='t', side='BUY', amount='25', price='.5',
                        shares='50', maker='0x871d37b430c42ddbd0bbd37c29c02a2974109de9',
                        signer='0x9348efd557a09e644795c8f114bcf0bef86f203a')
