"""Separate calibration ledger. No SDK, network, D6 mutation or auto-arming."""
from __future__ import annotations
import copy,hashlib,json,os,time,threading,sys
from decimal import Decimal
from pathlib import Path

VERSION='REAL_EXECUTION_CALIBRATION_V1'
ZERO=Decimal('0')

def dec(x):
 if isinstance(x,bool):raise ValueError('BOOLEAN_AMOUNT')
 v=Decimal(str(x))
 if not v.is_finite() or v<0:raise ValueError('INVALID_AMOUNT')
 return v

def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False,default=lambda x:str(x) if isinstance(x,Decimal) else (_ for _ in ()).throw(TypeError(type(x))))
def digest(x):return hashlib.sha256(encoded(x).encode()).hexdigest()
def allocate_experiment_id(directory, base_name="calibration-v1"):
    """Atomically allocate the next unused experiment ID.

    Uses a lock file + counter file so concurrent launches never collide.
    Scans existing .jsonl journals to seed the counter on first use.
    Returns e.g. 'calibration-v1-run0003'.
    Never overwrites or reuses an existing journal file.
    """
    import msvcrt, os, json, re
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "._run_counter.lock"
    counter_path = directory / "._run_counter.json"
    pattern = re.compile(r"^" + re.escape(base_name) + r"-run(\d{4})\.jsonl$")

    # Acquire exclusive lock
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o666)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        os.close(fd)
        raise OSError("CONCURRENT_LAUNCH_DETECTED: another launch holds the counter lock")
    try:
        if counter_path.exists():
            data = json.loads(counter_path.read_text())
            next_n = data["next"]
        else:
            # Seed: find highest existing run number
            max_n = 0
            for f in directory.iterdir():
                m = pattern.match(f.name)
                if m:
                    n = int(m.group(1))
                    if n > max_n:
                        max_n = n
            next_n = max_n + 1
            # Also check DURABLE_INTENT recovery journals (outside preparation/)
            # Only preparation/ matters for the lock file scope.

        experiment_id = f"{base_name}-run{next_n:04d}"
        # Double-check no journal file exists with this ID (safety net)
        journal_path = directory / f"{experiment_id}.jsonl"
        if journal_path.exists():
            raise FileExistsError(f"JOURNAL_COLLISION: {journal_path} exists despite counter {next_n}")

        # Write back incremented counter
        counter_path.write_text(json.dumps({"next": next_n + 1}, separators=(",", ":")))
        os.fsync(fd)
        return experiment_id
    finally:
        os.close(fd)


def redact(x):
 if isinstance(x,dict):return {k:('[REDACTED]' if any(t in k.lower().replace('_','') for t in ('secret','privatekey','signature','credential','authorization','apikey','passphrase','seedphrase')) else redact(v)) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [redact(v) for v in x]
 return x

class Journal:
 def __init__(self,path,experiment_id):
  self.lock=threading.RLock()
  self.path=Path(path);self.experiment_id=experiment_id;self.seq=0;self.previous='0'*64;self.failed=False;self.bytes=0
  self.file=self.path.open('xb',buffering=0)
 def append(self,kind,payload):
  with self.lock:return self._append(kind,payload)
 def _append(self,kind,payload):
  if self.failed:raise OSError('JOURNAL_FAILED')
  try:
   row={'experiment_id':self.experiment_id,'seq':self.seq,'previous':self.previous,'kind':kind,'payload':redact(payload)}
   row['hash']=digest(row);data=(encoded(row)+'\n').encode()
   if len(data)>1024**2 or self.bytes+len(data)>256*1024**2:raise OSError('JOURNAL_QUOTA')
   view=memoryview(data)
   while view:
    n=self.file.write(view)
    if not n:raise OSError('SHORT_WRITE')
    view=view[n:]
   os.fsync(self.file.fileno());self.seq+=1;self.previous=row['hash'];self.bytes+=len(data)
   return copy.deepcopy(row)
  except BaseException:self.failed=True;raise
 def close(self):
  with self.lock:self.file.close()
 @staticmethod
 def read(path):
  previous='0'*64;session=None
  with Path(path).open('rb') as f:
   for seq,line in enumerate(iter(lambda:f.readline(1024**2+1),b'')):
    if len(line)>1024**2 or not line.endswith(b'\n'):raise ValueError('JOURNAL_TORN')
    row=json.loads(line);h=row.pop('hash')
    if session is None:session=row['experiment_id']
    if row['seq']!=seq or row['previous']!=previous or row['experiment_id']!=session or digest(row)!=h:raise ValueError('JOURNAL_CORRUPT')
    row['hash']=h;previous=h;yield row

class CalibrationLedger:
 MAX_ENTRY=25;MAX_TOTAL=100;MAX_ENTRIES=4;MAX_CONCURRENT=1
 def __init__(self,journal,account,starting_cash):
  self.journal=journal;self.account=account;self.starting_cash=dec(starting_cash);self.allocated=ZERO;self.spent=ZERO;self.proceeds=ZERO;self.cash_fees=ZERO;self.share_fees=ZERO
  self.cash=self.starting_cash;self.positions={};self.orders={};self.fills={};self.shadows={};self.trades={};self.active=None;self.attempts=0;self.reconciled=False;self.stop=False;self.stop_new_entries=False;self.reasons=[];self.recovery_only=False;self.last_fill_receive_ms=0
  journal.append('INIT',{'account':account,'starting_cash':str(self.starting_cash),'version':VERSION,'max_entry':25,'max_total':100,'max_entries':4})
 def emit(self,kind,payload):
  try:return self.journal.append(kind,payload)
  except BaseException as exc:
   self.stop=True;self.stop_new_entries=True;self.reconciled=False
   if 'JOURNAL_FAILURE' not in self.reasons:self.reasons.append('JOURNAL_FAILURE')
   if not hasattr(self,'journal_failure'):
    self.journal_failure=exc
    # Independent sink, no payload or exception text (both may contain credentials).
    try:sys.stderr.write('JOURNAL_FAILURE exception_type='+type(exc).__name__+'; entries blocked\n');sys.stderr.flush()
    except BaseException:pass
   raise
 def halt(self,reason,details=None):
  self.stop=True
  if reason not in ('MANUAL_KILL','DISK_LOW','EXPERIMENT_EXPIRED','RESIDUAL_REQUIRES_OPERATOR_HANDOFF'):self.reconciled=False
  self.reasons.append(reason)
  self.emit('STOP',{'reason':reason,'details':redact(details or {})})
 def seal_shadow(self,opportunity,shadow):
  if opportunity in self.shadows:raise ValueError('SHADOW_ALREADY_SEALED')
  sealed=redact(copy.deepcopy(shadow))
  if hasattr(self.journal,'project_shadow'):sealed=self.journal.project_shadow(sealed)
  h=digest(sealed)
  self.emit('SHADOW_SEALED',{'opportunity_id':opportunity,'sha256':h,'shadow':sealed});self.shadows[opportunity]=(h,sealed);return h
 def reserve(self,opportunity,notional,fee_ceiling,fee_risk=None):
  n,f=dec(notional),dec(fee_ceiling)
  if self.stop or self.stop_new_entries or self.recovery_only or not self.reconciled:raise ValueError('ENTRIES_STOPPED_OR_UNRECONCILED')
  if self.active is not None or any(self.positions.values()):raise ValueError('ONE_POSITION_GATE')
  if opportunity not in self.shadows:raise ValueError('SHADOW_REQUIRED')
  if not ZERO<n<=25:raise ValueError('ENTRY_CAP_25')
  if self.attempts>=4 or self.allocated+n+f>100 or n+f>self.cash:raise ValueError('EXPERIMENT_CAP_100')
  if opportunity in self.trades:raise ValueError('DUPLICATE_OPPORTUNITY')
  self.emit('RESERVE',{'opportunity_id':opportunity,'notional':str(n),'fee_ceiling':str(f),'trade_number':self.attempts+1,'fee_risk':__import__('dataclasses').asdict(fee_risk) if fee_risk else None})
  self.trades[opportunity]={'notional':n,'fee_ceiling':f,'spent':ZERO,'proceeds':ZERO,'cash_fees':ZERO,'share_fees':ZERO,'reserved':n+f,'entry_terminal':False,'exit_terminal':False,'orders':[]}
  self.trades[opportunity]['fee_risk']=fee_risk
  self.allocated+=n+f;self.active=opportunity;self.attempts+=1;self.reconciled=False
 def intent(self,client_id,side,token,market,price,shares,notional,book,send_intent_ms):
  p,q,n=dec(price),dec(shares),dec(notional)
  if client_id in self.orders or self.active is None:raise ValueError('DUPLICATE_OR_UNRESERVED_ORDER')
  trade=self.trades[self.active]
  shadow_hash,shadow=self.shadows[self.active]
  if digest(shadow)!=shadow_hash or shadow.get('token')!=token or shadow.get('market')!=market:raise ValueError('SHADOW_IDENTITY_OR_HASH_MISMATCH')
  if side not in ('BUY','SELL') or not ZERO<p<1 or q<=0 or not token or not market:raise ValueError('ORDER_INVALID')
  if any(o['side']==side and o['opportunity_id']==self.active for o in self.orders.values()):raise ValueError('NO_AUTOMATIC_RETRY')
  if side=='BUY' and (self.stop or n>25 or n>trade['notional'] or p*q>25):raise ValueError('FORMATTED_ENTRY_CAP')
  if side=='SELL' and (not self.reconciled or not trade['entry_terminal'] or q>self.positions.get(token,ZERO)):raise ValueError('EXIT_QUANTITY_UNPROVEN')
  risk=trade.get('fee_risk')
  if side=='SELL' and risk and q+max(ZERO,dec(risk.outcome_shares)-trade['share_fees'])>self.positions.get(token,ZERO):raise ValueError('EXIT_SHARE_FEE_RESERVE')
  row={'client_id':client_id,'opportunity_id':self.active,'trade_number':self.attempts,'side':side,'token':token,'market':market,'price':str(p),'shares':str(q),'notional':str(n),'book':copy.deepcopy(book),'order_type':'FAK','send_intent_ms':send_intent_ms,'send_proven':False}
  self.emit('DURABLE_INTENT',row);self.orders[client_id]={**row,'order_id':None,'terminal':False,'filled_shares':ZERO,'filled_notional':ZERO,'reported_filled':None};trade['orders'].append(client_id);self.reconciled=False
 def ack(self,client_id,response,response_ms,send_ms=None):
  o=self.orders[client_id];self.emit('ACK_RESPONSE',{'client_id':client_id,'response':redact(response),'receive_ms':response_ms,'local_send_call_ms':send_ms})
  if o['order_id'] is not None:self.halt('DUPLICATE_ACK');return False
  if not isinstance(response,dict) or response.get('ok') is not True or not response.get('order_id'):
   self.halt('MISSING_OR_REJECTED_ACK');return False
  if any(x['order_id']==response['order_id'] for x in self.orders.values()):self.halt('DUPLICATE_ORDER_ID');return False
  o['order_id']=response['order_id'];return True
 def terminal(self,client_id,status,cumulative_shares):
  o=self.orders[client_id];q=dec(cumulative_shares)
  self.emit('ORDER_TERMINAL_OBSERVATION',{'client_id':client_id,'status':status,'cumulative_shares':str(q)})
  if not o['order_id'] or status not in ('FILLED','CANCELED','EXPIRED') or q!=o['filled_shares']:
   self.halt('UNKNOWN_ORDER_OR_FILL_STATE');return False
  o['terminal']=True;o['reported_filled']=q;self.trades[o['opportunity_id']]['entry_terminal' if o['side']=='BUY' else 'exit_terminal']=True;return True
 def fill(self,client_id,fill):
  o=self.orders[client_id];clean=redact(copy.deepcopy(fill));key=clean.get('trade_id')
  self.emit('FILL_OBSERVATION',{'client_id':client_id,'fill':clean})
  if key in self.fills:
   if self.fills[key]!=digest(clean):self.halt('DUPLICATE_FILL_CONFLICT');return False
   return True
  required=('trade_id','order_id','token','market','side','price','shares','cash_fee','share_fee','fee_evidence','exchange_ts_ms','receive_ts_ms')
  if any(k not in clean or clean[k] is None for k in required) or not key:self.halt('FILL_SCHEMA_UNKNOWN');return False
  if clean['order_id']!=o['order_id'] or any(clean[k]!=o[k] for k in ('token','market','side')):self.halt('FILL_IDENTITY_MISMATCH');return False
  if not isinstance(clean['fee_evidence'],dict) or clean['fee_evidence'].get('cash_effect_proven') is not True or clean['fee_evidence'].get('share_effect_proven') is not True:self.halt('FEE_EFFECT_UNPROVEN');return False
  try:p,q,cf,sf=map(dec,(clean['price'],clean['shares'],clean['cash_fee'],clean['share_fee']))
  except Exception:self.halt('FILL_AMOUNT_UNKNOWN');return False
  if not ZERO<p<1 or q<=0 or any(type(clean[k]) is not int or clean[k]<0 for k in ('exchange_ts_ms','receive_ts_ms')) or clean['exchange_ts_ms']>clean['receive_ts_ms']:self.halt('FILL_CLOCK_OR_PRICE_INVALID');return False
  t=self.trades[o['opportunity_id']];n=p*q
  if o['side']=='BUY':
   self.spent+=n;t['spent']+=n;self.cash-=n+cf;self.positions[o['token']]=self.positions.get(o['token'],ZERO)+q-sf
  else:
   self.proceeds+=n;t['proceeds']+=n;self.cash+=n-cf;self.positions[o['token']]=self.positions.get(o['token'],ZERO)-q-sf
  self.cash_fees+=cf;self.share_fees+=sf;t['cash_fees']+=cf;t['share_fees']+=sf;t['reserved']=max(ZERO,t['notional']+t['fee_ceiling']-t['spent']-t['cash_fees'])
  self.last_fill_receive_ms=max(self.last_fill_receive_ms,clean['receive_ts_ms'])
  self.fills[key]=digest(clean);o['filled_shares']+=q;o['filled_notional']+=n;self.reconciled=False
  risk=t.get('fee_risk')
  try:
   if risk is None and t['share_fees']:raise ValueError('FEE_UNITS_UNQUALIFIED')
   observed_fee=risk.observed_cash(t['cash_fees'],t['share_fees'],clean['receive_ts_ms']) if risk else t['cash_fees']
   if risk and (t['cash_fees']>dec(risk.cash_collateral) or t['share_fees']>dec(risk.outcome_shares)):raise ValueError('OBSERVED_FEE_BOUND_BREACH')
  except ValueError as exc:self.halt(str(exc));return False
  if ((o['side']=='BUY' and p>dec(o['price'])) or (o['side']=='SELL' and p<dec(o['price'])) or t['spent']>t['notional'] or observed_fee>t['fee_ceiling'] or self.positions[o['token']]<0 or self.cash<0 or (o['side']=='SELL' and o['filled_shares']>dec(o['shares']))):
   self.halt('OBSERVED_BUDGET_OR_EXPOSURE_BREACH');return False
  return True
 def reconcile(self,snapshot,now_ms):
  self.emit('RECONCILIATION_OBSERVATION',{'snapshot':redact(snapshot),'decision_ms':now_ms})
  try:
   proofs=('inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete')
   if snapshot['account']!=self.account:raise ValueError('ACCOUNT_MISMATCH')
   if any(snapshot.get(x) is not True for x in proofs):raise ValueError('ACCOUNT_SCOPE_UNPROVEN')
   if snapshot['observed_ms']<self.last_fill_receive_ms or not 0<=now_ms-snapshot['observed_ms']<=5000:raise ValueError('ACCOUNT_STALE_OR_FUTURE')
   if snapshot.get('open_orders'):raise ValueError('UNKNOWN_OPEN_ORDER')
   if dec(snapshot['cash'])!=self.cash:raise ValueError('BALANCE_MISMATCH')
   pos={k:dec(v) for k,v in snapshot['positions'].items() if dec(v)!=0}
   if pos!={k:v for k,v in self.positions.items() if v!=0}:raise ValueError('POSITION_MISMATCH')
   if set(snapshot['trade_ids'])!=set(self.fills):raise ValueError('TRADE_HISTORY_MISMATCH')
   known={o['order_id'] for o in self.orders.values() if o['order_id']}
   if set(snapshot['terminal_order_ids'])!=known or any(not o['terminal'] or o['reported_filled']!=o['filled_shares'] for o in self.orders.values()):raise ValueError('ORDER_STATE_UNKNOWN')
  except (KeyError,ValueError,TypeError,ArithmeticError) as exc:self.halt(str(exc));return False
  self.last_account_snapshot=copy.deepcopy(snapshot)
  self.reconciled=True;self.emit('RECONCILED',{'CALIBRATION_ACCOUNT_RECONCILED':True,'decision_ms':now_ms,'D6_current_inventory_proven':False})
  if self.active and not any(self.positions.values()):
   t=self.trades[self.active]
   if t['entry_terminal'] and (t['spent']==0 or t['exit_terminal']):t['reserved']=ZERO;self.active=None
  return True
 def report(self):
  flat=not any(self.positions.values());known=self.reconciled
  return {'version':VERSION,'starting_experiment_budget':'100','maximum_allowed_budget':'100','starting_account_cash':str(self.starting_cash),'total_committed_notional':str(sum((x['notional'] for x in self.trades.values()),ZERO)),'lifetime_allocated_including_fee_ceiling':str(self.allocated),'reserved_amount':str(sum((x['reserved'] for x in self.trades.values()),ZERO)),'realized_spent_notional':str(self.spent),'realized_proceeds':str(self.proceeds),'actual_fees':{'collateral_cash':str(self.cash_fees),'outcome_shares':str(self.share_fees)},'remaining_experiment_budget':str(Decimal(100)-self.allocated),'open_exposure':{k:str(v) for k,v in self.positions.items() if v},'open_exposure_at_risk_upper_bound':str(self.allocated) if not flat or self.active is not None else '0','exposure_known':known,'net_realized_pnl':str(self.cash-self.starting_cash) if flat and known else None,'gross_realized_pnl':str(self.proceeds-self.spent) if flat and known and self.share_fees==0 else None,'entries_attempted':self.attempts,'orders_attempted':len(self.orders),'orders_accepted':sum(o['order_id'] is not None for o in self.orders.values()),'fills':len(self.fills),'partial_fills':sum(o['terminal'] and 0<o['filled_shares']<dec(o['shares']) for o in self.orders.values()),'no_fills':sum(o['terminal'] and o['filled_shares']==0 for o in self.orders.values()),'CALIBRATION_ACCOUNT_RECONCILED':self.reconciled,'STOP_NEW_ENTRIES':self.stop or self.stop_new_entries,'reasons':self.reasons.copy(),'SYSTEM_READY':False,'current_inventory_proven':False,'submit_allowed':False}

 def custody_snapshot(self):
  # Content revision changes for intents/ACKs/fills/terminality, never monitor writes.
  exposure={'account':self.account,'active':self.active,'positions':{k:str(v) for k,v in self.positions.items()},'cash':str(self.cash),'orders':copy.deepcopy(self.orders),'fills':copy.deepcopy(self.fills)}
  # Orders include local client IDs BEFORE a remote order ID exists.
  revision=digest(exposure)
  return {'account':self.account,'experiment_id':self.journal.experiment_id,'exposure':exposure,'exposure_revision':revision,'exposure_digest':revision,'journal_sequence':self.journal.seq}

 def checkpoint(self):return self.emit('CHECKPOINT',{'report':self.report(),'journal_previous':self.journal.previous,'journal_sequence':self.journal.seq,'arm_persisted':False})
 @staticmethod
 def recover(path):
  rows=list(Journal.read(path));pending={};shadows={};fills={}
  for row in rows:
   k,p=row['kind'],row['payload']
   if k=='SHADOW_SEALED':
    if digest(p['shadow'])!=p['sha256'] or p['opportunity_id'] in shadows:raise ValueError('SHADOW_CORRUPTION')
    shadows[p['opportunity_id']]=p['sha256']
   if k=='DURABLE_INTENT':pending[p['client_id']]=p
   if k=='FILL_OBSERVATION':fills.setdefault(p['fill'].get('trade_id'),[]).append(p)
   if k=='CHECKPOINT' and (p['journal_previous']!=row['previous'] or p['journal_sequence']!=row['seq']):raise ValueError('CHECKPOINT_CORRUPTION')
  return {'verified_rows':rows,'intent_evidence':pending,'fill_evidence':fills,'shadow_hashes':shadows,'STOP_NEW_ENTRIES':True,'armed':False,'mode':'MANUAL_RECOVERY_ONLY','CALIBRATION_ACCOUNT_RECONCILED':False,'exposure_known':False,'resume_allowed':False}
