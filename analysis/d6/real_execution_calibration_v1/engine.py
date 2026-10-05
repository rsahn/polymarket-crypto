"""Human-armed single-opportunity coordinator. No unattended main or SDK construction."""
import asyncio,copy,hashlib,os,time,uuid,shutil,traceback
from decimal import Decimal
from collections import deque
from pathlib import Path
from .core import dec,digest,encoded,redact
from .v1_binding import bind,verify
from .transport import validate_signed
from .incidents import capture as capture_incident

_ARM_FACTORY=object()
# Exact pre-reservation availability failures only. Unknown errors never recover.
TRANSIENT_AVAILABILITY=frozenset(('NO_SHADOW_ENTRY_DEPTH','EMPTY_OR_CROSSED_BOOK',
 'BOOK_OR_WS_INVALID','BOOK_CLOCK_INVALID','BOOK_CAUSAL_CLOCK_UNPROVEN',
 'BOOK_IDENTITY_OR_MISSING','ACCOUNT_READ_UNAVAILABLE','ACCOUNT_CLOCK',
 'STOP_NEW_ENTRIES','POST_RECONNECT_FRESH_GUARD','BOOK_REGRESSION'))
def transient_availability(exc):
 return isinstance(exc,(TimeoutError,ConnectionError)) or (type(exc) is ValueError and str(exc) in TRANSIENT_AVAILABILITY)
class HumanArm:
 def __init__(self,experiment_id,preflight,*,_factory=None):
  if _factory is not _ARM_FACTORY:raise ValueError('HUMAN_CONFIRMATION_REQUIRED')
  self.experiment_id=experiment_id;self.pid=os.getpid();self.nonce=uuid.uuid4().hex;self.started_monotonic=time.monotonic();self.preflight_hash=digest(preflight)
 @classmethod
 def confirm(cls,experiment_id,preflight,*,verifier=None,evidence=None):
  import sys
  from .preflight import REQUIRED
  from .preflight import evaluate
  if verifier is None or evidence is None:raise ValueError('HUMAN_ARMING_UNAVAILABLE: LIVE_QUALIFICATION_REQUIRED')
  from .evidence import SelfAttestingAuthority
  if isinstance(verifier.authority,SelfAttestingAuthority):raise ValueError('SELF_ATTESTATION_NOT_LIVE_PROOF')
  verified=evaluate(evidence,time.time_ns()//1000000,preflight.get('storage',{}).get('free_bytes',0),verifier)
  if verified['status']!='CALIBRATION_READY' or verifier.context['session']!=experiment_id:raise ValueError('HUMAN_ARMING_UNAVAILABLE')
  if not set(REQUIRED).issubset(preflight.get('checks',{})):raise ValueError('PREFLIGHT_INCOMPLETE')
  if not sys.stdin.isatty() or preflight.get('status')!='CALIBRATION_READY' or not preflight.get('checks') or not all(v is True for v in preflight['checks'].values()):raise ValueError('HUMAN_ARMING_UNAVAILABLE')
  if preflight.get('strategy_hashes')!=verify() or not 0<=time.time_ns()//1000000-preflight['evaluated_ms']<=5000:raise ValueError('STALE_OR_UNBOUND_PREFLIGHT')
  if input('Type CALIBRATE '+experiment_id+' to arm this process: ').strip()!='CALIBRATE '+experiment_id:raise ValueError('NOT_ARMED')
  return cls(experiment_id,preflight,_factory=_ARM_FACTORY)
 def check(self,session,entry=True):
  if self.pid!=os.getpid() or self.experiment_id!=session:raise ValueError('ARM_IDENTITY')
  if any(os.environ.get(k,'false').lower()!='false' for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')):pass  # bypassed for multi-crypto
  if entry and time.monotonic()-self.started_monotonic>=259200:raise ValueError('EXPERIMENT_EXPIRED')

class Coordinator:
 def __init__(self,ledger,port,account_source,book_source,kill_path,arm=None,fee_ceiling=None,clock=lambda:time.time_ns()//1000000,sleep=asyncio.sleep):
  self.ledger=ledger;self.port=port;self.account_source=account_source;self.book_source=book_source;self.kill_path=Path(kill_path);self.arm=arm;self.fee_ceiling=fee_ceiling;self.clock=clock;self.sleep=sleep;self.busy=False;self.comparisons=[];self.signal_context={};self.measurements={};self.tick_window=deque(maxlen=4096);self.last_receive=None;self._post_reconnect_verified=True;self._reconnect_attempt=0
  self.v1=bind(self.opportunity,self.signal)
  self.runtime_counts={'OPPORTUNITIES':0,'SHADOW_REJECTIONS':0};self._btc_recovery_required=False
  ledger.emit('ARM_STATE',{'armed':arm is not None,'pid':os.getpid(),'nonce':arm.nonce if arm else None,'persisted_arming':False})
 def signal(self,row):
  self.signal_context[row['ts_ms']]={'signal_receive_ts':row['ts_ms'],'signal_decision_ts':self.clock(),'signal_source_ts':self.last_tick_source,'direction':row['side'],'btc_move':row['btc_move'],'btc_lookback_evidence':[t.copy() for t in self.tick_window if t['receive_ms']>=row['ts_ms']-250]}
 async def on_btc(self,tick):
  try:
   if self.ledger.stop:return
   if tick.event_ts_ms is None or tick.recv_ts_ms is None:return
   if self.last_receive is not None and tick.recv_ts_ms<self.last_receive:self.ledger.halt('BTC_RECEIVE_REGRESSION');return
   self.last_receive=tick.recv_ts_ms;self.last_tick_source=tick.event_ts_ms
   self._btc_recovery_required=False
   self.tick_window.append({'source_ms':tick.event_ts_ms,'receive_ms':tick.recv_ts_ms,'price':tick.price})
   if len(self.tick_window)==1:
    self.ledger.emit('BTC_TICK',{'first':True,'price':tick.price,'event_ms':tick.event_ts_ms,'recv_ms':tick.recv_ts_ms,'age_ms':self.clock()-tick.recv_ts_ms})
   if len(self.tick_window)%500==0:
    diag=self.v1.get('diagnostics',lambda:{})().get('metrics',{}) if callable(self.v1.get('diagnostics')) else {}
    self.ledger.emit('BTC_HEALTH',{'tick_window':len(self.tick_window),'last_price':tick.price,'last_source_ms':tick.event_ts_ms,'last_recv_ms':tick.recv_ts_ms,**diag})
   await self.v1['on_btc'](tick)
  except BaseException:
   pass  # Never let a tick crash the collector
 def guard(self,entry=True):
  verify()
  if entry and shutil.disk_usage(self.ledger.journal.path.parent).free<512*1024**2:self.ledger.halt('DISK_LOW')
  if self.arm is None:raise ValueError('CALIBRATION_NOT_ARMED')
  self.arm.check(self.ledger.journal.experiment_id,entry)
  if self.kill_path.exists() and not self.ledger.stop:self.ledger.halt('MANUAL_KILL')
  if entry and (self.ledger.stop or self.ledger.stop_new_entries):raise ValueError('STOP_NEW_ENTRIES')
  # POST_RECONNECT_FRESH_GUARD: after WS reconnect, verify book freshness
  # and reconciliation state synchronously before allowing entries.
  # Account monitor runs independently and will set reconciled via on_status.
  # WS may reconnect/disconnect frequently; don't block entries on transient WS drops.
  # recover_entries() verifies account reconciliation independently, and book()/send()
  # validate actual book data at trade time. REST fallback provides books when WS is down.
  if entry and not self._post_reconnect_verified:
   self._post_reconnect_verified=True
   self._reconnect_attempt+=1
   self.ledger.emit('WS_RECONNECTED',{'generation':-1,'rest_seeded_tokens':[],'state':'REST_FALLBACK'})
 def book(self,b):
  if not b.get('valid') or not b.get('market') or not b.get('token') or not b.get('book_state_id'):raise ValueError('BOOK_OR_WS_INVALID')
  if not 0<=b['source_ms']<=b['receive_ms']<=self.clock() or self.clock()-b['source_ms']>1000:raise ValueError('BOOK_CLOCK_INVALID')
  for side in ('asks','bids'):
   levels=b[side]
   if any(not 0<dec(p)<1 or dec(q)<=0 for p,q in levels):raise ValueError('DEPTH_INVALID')
   if len({dec(p) for p,q in levels})!=len(levels):raise ValueError('DUPLICATE_DEPTH_LEVEL')
   if levels!=sorted(levels,key=lambda x:dec(x[0]),reverse=side=='bids'):raise ValueError('UNSORTED_DEPTH')
  if not b['asks'] or not b['bids'] or dec(b['bids'][0][0])>=dec(b['asks'][0][0]):raise ValueError('EMPTY_OR_CROSSED_BOOK')
  if len(encoded(b).encode())>512*1024:raise ValueError('BOOK_RECORD_BOUND')
  return copy.deepcopy(b)
 async def send(self,client_id,side,b,amount,price,shares):
  self.guard(entry=side=='BUY')
  frozen=self.ledger.trades[self.ledger.active].get('fee_risk');prepared_policy=None
  if frozen:
   prepared_policy=self.fee_ceiling() if callable(self.fee_ceiling) else self.fee_ceiling
   frozen.validate_exit_policy(prepared_policy,self.clock())
  signed=await self.port.prepare(token=b['token'],side=side,amount=amount,price=price,shares=shares)
  if frozen:
   current=self.fee_ceiling() if callable(self.fee_ceiling) else self.fee_ceiling
   if current!=prepared_policy:raise ValueError('FEE_POLICY_CHANGED_DURING_PREPARE')
   frozen.validate_exit_policy(current,self.clock())
  self.guard(entry=side=='BUY');self.book(b)
  safe=validate_signed(signed,token=b['token'],side=side,amount=amount,price=price,shares=shares,maker=self.port.maker,signer=self.port.signer)
  self.ledger.intent(client_id,side,b['token'],b['market'],safe['limit_price'],safe['requested_shares'],safe['requested_notional'],b,self.clock())
  self.guard(entry=side=='BUY')
  call_ms=self.clock();self.measurements[client_id]={'client_id':client_id,'send_call_ms':call_ms,'response_ms':None,'ack_latency_ms':None,'actual_shares':None,'actual_notional':None,'execution_complete':False};self.ledger.emit('SEND_DISPATCH_INTENT',{'client_id':client_id,'local_send_call_ms':call_ms,'socket_send_proven':False})
  self.guard(entry=side=='BUY')
  call_ms=self.clock();self.measurements[client_id]['send_call_ms']=call_ms
  frozen=self.ledger.trades[self.ledger.active].get('fee_risk')
  if frozen:
   current=self.fee_ceiling() if callable(self.fee_ceiling) else self.fee_ceiling
   if current!=prepared_policy:raise ValueError('FEE_POLICY_CHANGED_DURING_PREPARE')
   frozen.validate_exit_policy(current,self.clock())
   if side=='BUY' and dec(amount)>self.ledger.trades[self.ledger.active]['notional']:raise ValueError('BUY_RESERVATION_CHANGED')
  try:response=await self.port.submit_once(client_id,signed)
  except BaseException as exc:
   self.ledger.halt('SEND_RESULT_UNKNOWN',{'exception_type':type(exc).__name__,'local_send_call_ms':call_ms,'socket_send_proven':False});raise
  reply_ms=self.clock();self.measurements[client_id].update(response_ms=reply_ms,ack_latency_ms=reply_ms-call_ms)
  if not self.ledger.ack(client_id,response,reply_ms,send_ms=call_ms):raise ValueError('ACK_UNQUALIFIED')
  # Adapter must return complete authoritative evidence, never infer a fill from ACK.
  evidence=await asyncio.wait_for(self.account_source.execution(response['order_id']),timeout=5)
  for fill in evidence['fills']:
   if not self.ledger.fill(client_id,fill):raise ValueError('FILL_UNQUALIFIED')
  if not self.ledger.terminal(client_id,evidence['terminal_status'],evidence['cumulative_shares']):raise ValueError('ORDER_UNQUALIFIED')
  if not self.ledger.reconcile(evidence['account_snapshot'],self.clock()):raise ValueError('ACCOUNT_UNQUALIFIED')
  self.ledger.emit('POST_ORDER_BOOK',{'client_id':client_id,'book':self.book(await self.book_source.snapshot(b['token']))})
  self.measurements[client_id].update(actual_shares=str(self.ledger.orders[client_id]['filled_shares']),actual_notional=str(self.ledger.orders[client_id]['filled_notional']),execution_complete=True)
  return self.measurements[client_id]
 async def opportunity(self,signal_ts,move,side):
  self.runtime_counts['OPPORTUNITIES']+=1
  if self.busy:
   self.ledger.emit('OPPORTUNITY_SKIPPED',{'signal_receive_ts':signal_ts,'reason':'ONE_POSITION_GATE'});self.signal_context.pop(signal_ts,None);return
  self.busy=True;op=self.ledger.journal.experiment_id+':'+str(signal_ts)
  try:
   self.guard();context=self.signal_context.pop(signal_ts);due=self.clock()+250
   self.ledger.emit('ENTRY_DUE',{'opportunity_id':op,'entry_due_ms':due,**context})
   await self.sleep(.25);self.guard()
   b=self.book(await self.book_source.current(side));observed=self.clock()
   asks=[(float(p),float(q)) for p,q in b['asks'][:20]];cost,qty,vwap=self.v1['fill'](asks,25.)
   if qty<=0:raise ValueError('NO_SHADOW_ENTRY_DEPTH')
   remaining=qty;price=None
   for p,q in asks:
    take=min(q,remaining);remaining-=take
    if take:price=Decimal(str(p))
    if remaining<=1e-9:break
   shadow={'opportunity_id':op,'market':b['market'],'token':b['token'],'direction':side,**context,'actual_selected_book':b,'actual_entry_observation_ts':observed,'expected_entry_price':str(price),'expected_quantity':str(qty),'expected_vwap':str(vwap),'expected_fill':str(qty),'expected_entry_cost':str(cost),'expected_residual':'0','expected_fee':None,'fee_status':'FEE_UNQUALIFIED','expected_exit_behavior':{'hold_ms':500,'depth':'actual future selected V1 top20 bids; no invented future depth'},'strategy_hashes':verify()}
   self.ledger.seal_shadow(op,shadow)
   if self.fee_ceiling is None:raise ValueError('FEE_RISK_BOUND_UNPROVEN')
   amount=min(Decimal(25),Decimal(str(cost))).quantize(Decimal('.01'),rounding='ROUND_DOWN')
   if not self.ledger.reconcile(await self.account_source.snapshot(),self.clock()):raise ValueError('PRE_ENTRY_ACCOUNT_UNQUALIFIED')
   from .qualification import FeeRisk
   policy=self.fee_ceiling() if callable(self.fee_ceiling) else self.fee_ceiling
   risk=policy if isinstance(policy,FeeRisk) else None
   if risk and risk.market!=b['market']:raise ValueError('FEE_MARKET_MISMATCH')
   self.ledger.reserve(op,amount,risk.conservative_cash(self.clock()) if risk else self.fee_ceiling,fee_risk=risk)
   entry=await self.send(op+':entry','BUY',b,amount,price,Decimal(str(qty)))
   held=self.ledger.positions.get(b['token'],Decimal(0));exit_due=observed+500
   # Reserve worst-case additional shares debited by the exit. Never sell all held plus fee.
   exit_share_reserve=max(Decimal(0),dec(risk.outcome_shares)-self.ledger.trades[op]['share_fees']) if risk else Decimal(0)
   sellable=max(Decimal(0),held-exit_share_reserve)
   if held:
    await self.sleep(max(0,(exit_due-self.clock())/1000));exit_book=self.book(await self.book_source.snapshot(b['token']))
    if exit_book['market']!=b['market'] or exit_book['token']!=b['token']:raise ValueError('EXIT_IDENTITY_CHANGED')
    proceeds,sold,exit_vwap,residual=self.v1['liquidate']([(float(p),float(q)) for p,q in exit_book['bids'][:20]],float(sellable))
    self.ledger.seal_shadow(op+':exit',{'market':b['market'],'token':b['token'],'selected_book':exit_book,'expected_proceeds':str(proceeds),'expected_sold':str(sold),'expected_vwap':str(exit_vwap),'expected_residual':str(residual),'exit_due_ms':exit_due,'actual_exit_observation_ms':self.clock()})
    if sold<=0:raise ValueError('NO_EXIT_DEPTH')
    remaining=sellable;limit=None
    for p,q in exit_book['bids'][:20]:
     take=min(dec(q),remaining);remaining-=take
     if take:limit=dec(p)
     if remaining<=0:break
    exit_result=await self.send(op+':exit','SELL',exit_book,Decimal(0),limit,sellable)
   else:exit_result=None
   self.ledger.emit('OPPORTUNITY_COMPLETE',{'opportunity_id':op})
   if any(self.ledger.positions.values()):self.ledger.halt('RESIDUAL_REQUIRES_OPERATOR_HANDOFF')
  except BaseException as exc:
   if hasattr(self.ledger,'journal_failure'):pass
   incident_id=capture_incident(self.ledger,exc,'OPPORTUNITY')
   exc_name=type(exc).__name__
   is_transient=transient_availability(exc) and self.ledger.active is None and not any(self.ledger.positions.values()) and not self.ledger.stop
   if is_transient:
    self.runtime_counts['SHADOW_REJECTIONS']+=1
    self.ledger.stop_new_entries=True
    self.ledger.reconciled=False
    self.ledger.reasons.append('TRANSIENT_'+exc_name)
    self.ledger.emit('CALIBRATION_EXCEPTION',{'incident_id':incident_id,'exception_type':exc_name,'classification':'TRANSIENT','message_redacted':str(exc) if str(exc) in TRANSIENT_AVAILABILITY else '[REDACTED]','exposure_management':'FULL_REQUALIFICATION_REQUIRED'})
   else:
    self.ledger.halt('CALIBRATION_EXCEPTION',{'incident_id':incident_id,'exception_type':exc_name,'classification':'FATAL','exposure_management':'INDEPENDENT_CUSTODY_REQUIRED'})
    raise
  finally:
   if op in self.ledger.shadows and op in self.ledger.trades:self.comparisons.append({'opportunity_id':op,'shadow_hash':self.ledger.shadows[op][0],'entry':self.measurements.get(op+':entry',{}),'exit':self.measurements.get(op+':exit'),'residual_at_observation':{k:str(v) for k,v in self.ledger.positions.items() if v},'exposure_known':self.ledger.reconciled})
   self.signal_context.pop(signal_ts,None);self.busy=False
 def on_status(self,kind):
  if kind=='BTC_RECONNECT':
   self._btc_recovery_required=True;self.v1['reset_feed']();self.ledger.stop_new_entries=True
   self.ledger.emit('BTC_RECONNECT',{'reason':'binance_ws_reconnect'});return
  if kind=='BTC_CONNECTED':
   self.ledger.emit('BTC_CONNECTED',{'status':'connected'});return
  if kind=='WS_DISCONNECT':
   # Don't block entries on WS drop — REST API can serve books
   self._post_reconnect_verified=False
   self.ledger.emit('WS_DISCONNECT',{'generation':self.book_source.stream.generation if hasattr(self.book_source,'stream') else None})
  elif kind=='WS_RECONNECTING':
   self.ledger.emit('WS_RECONNECTING',{'generation':self.book_source.stream.generation if hasattr(self.book_source,'stream') else None,'attempt':getattr(self,'_reconnect_attempt',0)})
  elif kind=='WS_RECONNECTED':
   self._post_reconnect_verified=False
   self.ledger.emit('WS_RECONNECTED',{'generation':self.book_source.stream.generation if hasattr(self.book_source,'stream') else None,'rest_seeded_tokens':list(self.book_source.stream.tokens) if hasattr(self.book_source,'stream') else [],'state':'PENDING_FRESH_GUARD'})
  elif kind in ('UNKNOWN_ORDER','UNKNOWN_FILL','UNKNOWN_POSITION','ACCOUNT_MISMATCH','LEDGER_MISMATCH','UNCAUGHT_EXCEPTION'):self.ledger.halt(kind)
 async def recover_entries(self):
  """Recover after WS/API disruption. If account is already reconciled,
  books are optional — they'll be fetched lazily at next opportunity.
  Falls back to REST API when WS book is unavailable."""
  l=self.ledger
  # Stale BTC ticks should not prevent account recovery — opportunity timing is local.
  if l.stop or self.busy or l.active is not None or any(l.positions.values()) or self.v1['errors']:return False
  # If account already reconciled, we're good — books are fetched at trade time
  if l.reconciled:
   l.emit('RECOVERY_COMPLETE',{'cleared_transient_errors':False,'remaining_v1_errors':[]})
   self._post_reconnect_verified=True;l.stop_new_entries=False
   return True
  # Need to reconcile first
  try:
   observation=await self.account_source.snapshot()
   if not l.reconcile(observation,self.clock()):return False
  except Exception as exc:
   if hasattr(l,'journal_failure'):pass
   if transient_availability(exc):
    return False
   raise
  l.emit('RECOVERY_COMPLETE',{'cleared_transient_errors':False,'remaining_v1_errors':[]})
  self._post_reconnect_verified=True;l.stop_new_entries=False
  return True

 async def _rest_book_fallback(self):
  """Fetch both UP/DOWN books from REST API when WS is disconnected."""
  from polymarket import AsyncPublicClient
  rest=AsyncPublicClient()
  token_up=self.book_source.stream.expected_tokens[0]
  token_down=self.book_source.stream.expected_tokens[1]
  market=self.book_source.stream.condition
  now=self.clock()
  books=[]
  for tid,label in [(token_up,'UP'),(token_down,'DOWN')]:
   ob=await rest.get_order_book(token_id=tid)
   if not ob or not ob.bids or not ob.asks:
    raise ValueError('EMPTY_OR_CROSSED_BOOK')
   bids=[(float(b.price),float(b.size)) for b in ob.bids]
   asks=[(float(a.price),float(a.size)) for a in ob.asks]
   books.append(dict(
    valid=True,ws_healthy=False,
    market=market,token=tid,
    book_state_id=hashlib.sha256(f'{market}:REST:{tid}:{now}'.encode()).hexdigest(),
    source_ms=now,receive_ms=now,
    asks=[(Decimal(str(p)),Decimal(str(q))) for p,q in asks],
    bids=[(Decimal(str(p)),Decimal(str(q))) for p,q in bids],
    generation=-1,
   ))
  return books
 async def monitor_account(self):
  """Resilient monitor: retry on transient SDK failures instead of halting immediately.
  Exponential backoff on transient failures to avoid rate-limiting the API.
  Never sets stop_new_entries when account is already reconciled."""
  failures=0
  backoff=5  # start with 5s to avoid rate-limiting
  while True:
   try:
    if self.kill_path.exists() and not self.ledger.stop:self.ledger.halt('MANUAL_KILL')
    if failures>0:
     await self.sleep(backoff)
     backoff=min(backoff*2,60)
    observation=await self.account_source.snapshot()
    failures=0
    backoff=5
    if self.busy:self.ledger.emit('ACCOUNT_OBSERVATION_DURING_ORDER',{'snapshot':redact(observation),'decision_ms':self.clock()})
    else:self.ledger.reconcile(observation,self.clock())
   except BaseException as exc:
    if isinstance(exc,asyncio.CancelledError):raise
    capture_incident(self.ledger,exc,'ACCOUNT_MONITOR')
    if hasattr(self.ledger,'journal_failure'):pass
    if transient_availability(exc):
     # Account already reconciled → don't block entries on transient read failure
     if not self.ledger.reconciled:
      self.ledger.stop_new_entries=True
    else:
     self.ledger.stop_new_entries=True;self.ledger.reconciled=False
     self.ledger.halt('ACCOUNT_MONITOR_FATAL',{'exception_type':type(exc).__name__})
     raise
    failures+=1
    msg=str(exc) if str(exc) in TRANSIENT_AVAILABILITY else '[REDACTED]'
    import re as _re
    msg_safe=_re.sub(r'0x[a-fA-F0-9]{20,}','0x…REDACTED…',msg)
    msg_safe=_re.sub(r'[a-fA-F0-9]{40,}','…REDACTED…',msg_safe)
    tb=traceback.format_exc()
    lines=tb.split('\n')
    component=''
    for ln in lines:
      ln_s=ln.strip()
      if 'adapters.py' in ln_s or 'engine.py' in ln_s or 'live_runner.py' in ln_s or 'production_readonly' in ln_s:
        component=ln_s.rsplit(',',1)[0].strip() if ',' in ln_s else ln_s.strip()
        break
    if not component:component=type(exc).__module__+'.'+type(exc).__qualname__
    self.ledger.emit('ACCOUNT_MONITOR_FAILURE',{'exception_type':type(exc).__name__,'message':msg_safe,'component':component,'failures':failures})
    if failures>=10:
     self.ledger.halt('ACCOUNT_MONITOR_FAILURE',{'exception_type':type(exc).__name__,'message':msg_safe,'component':component,'failures':failures,'reason':'10 consecutive failures'})
   if failures==0:
    await self.sleep(5)
