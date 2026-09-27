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
 with pytest.raises(OSError):reserve(l)
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

@pytest.mark.parametrize('kind',['WS_DISCONNECT','UNKNOWN_ORDER','UNKNOWN_POSITION','ACCOUNT_MISMATCH','LEDGER_MISMATCH','UNCAUGHT_EXCEPTION'])
def test_kill_reasons_keep_exposure(tmp_path,kind):
 l=ledger(tmp_path);reserve(l);intent(l);fill(l)
 c=Coordinator(l,None,None,None,tmp_path/'kill');c.on_status(kind)
 assert l.stop and l.positions['t']==50;l.journal.close()

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
