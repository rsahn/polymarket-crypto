"""Technical NO_TRADE capture primitives; independent of D6 runtime and economic evaluation."""
from __future__ import annotations
import ast,asyncio,copy,hashlib,json,os,struct,time,types,zlib
from collections import deque
from pathlib import Path
from analysis.d6.prospective_v1.core import Seal,safety,encode,digest
from analysis.d6.prospective_v1.observability_v2 import observed_tree,strip_observations
VERSION='CAUSAL_CAPTURE_V1_R2'
GIB=1024**3
LIMITS={'RAW':64*GIB,'BOOK_META':16*GIB,'CAUSAL':8*GIB,'CHECKPOINT':256*1024**2,'CONTROL':16*1024**2}
MAX_RECORD=8*1024**2
RECOVERY_SCRATCH=GIB

def storage_preflight(free):
 total=sum(LIMITS.values())+RECOVERY_SCRATCH;margin=(total+4)//5;required=total+margin
 return {'status':'PASS' if free>=required else 'CAPTURE_24H_STORAGE_BLOCKED','archive_projection_bytes':21999279027,'enforced_byte_quotas':LIMITS.copy(),'scratch_recovery_bytes':RECOVERY_SCRATCH,'engineering_margin_bytes':margin,'required_bytes':required,'current_free_bytes':free,'additional_bytes_required':max(0,required-free),'qualification':'Quota-bounded capture, not a guarantee that unknown future traffic fits. Reaching any limit invalidates completeness and stops capture without dropping accepted data.'}

def source_seal(root):
 names=['analysis/run_d6_paper_live.py','analysis/d6/paper_live.py','analysis/d6/prospective_24h_v1/PROTOCOL.json','analysis/d6/prospective_24h_v1/criteria.json','analysis/d6/prospective_v1/observability_v2.py','backend/app/collectors/polymarket_ws.py','backend/app/collectors/polymarket.py','backend/app/d5/clock51.py','backend/app/d5/protocol51.py','analysis/d6/prospective_v1/core.py','analysis/d6/causal_capture_24h_v1/collector.py']
 runner=Path(root)/'analysis/d6/causal_capture_24h_v1/runner.py'
 if runner.exists():names.append(runner.relative_to(root).as_posix())
 return Seal.create(root,names)

class Journal:
 """One canonical append-only zlib frame per event, strict hash chain, byte quotas."""
 def __init__(self,path,session,limits=None):
  safety();self.path=Path(path);self.session=session;self.limits=LIMITS.copy() if limits is None else dict(limits);self.used={k:0 for k in self.limits};self.seq=0;self.prev='0'*64;self.failed=False;self.f=self.path.open('xb',buffering=0)
 def _write(self,b):
  view=memoryview(b)
  while view:
   n=self.f.write(view)
   if not n:raise OSError('SHORT_WRITE')
   view=view[n:]
 def append(self,bucket,payload,seq=None):
  if self.failed:raise OSError('JOURNAL_FAILED')
  if seq is not None and seq!=self.seq:raise ValueError('DUPLICATE_OR_OUT_OF_ORDER')
  if bucket not in self.limits:raise ValueError('UNKNOWN_BUCKET')
  row={'session':self.session,'seq':self.seq,'previous':self.prev,'bucket':bucket,'payload':payload}
  raw=encode(row).encode()
  if len(raw)>MAX_RECORD:raise ValueError('RECORD_BOUND_EXCEEDED')
  h=hashlib.sha256(raw).digest();compressed=zlib.compress(raw,1);frame=struct.pack('>I',len(compressed))+h+compressed
  try:
   if self.used[bucket]+len(frame)>self.limits[bucket]:raise OSError('CAPTURE_QUOTA_EXCEEDED:'+bucket)
   self._write(frame)
   self.used[bucket]+=len(frame);self.prev=h.hex();self.seq+=1
   if bucket=='CHECKPOINT' or self.seq%32==0:self.flush()
  except BaseException:self.failed=True;raise
  return row['seq']
 def flush(self):
  try:self.f.flush();os.fsync(self.f.fileno())
  except BaseException:self.failed=True;raise
 def checkpoint(self,state):return self.append('CHECKPOINT',{'previous_seq':self.seq-1,'previous_hash':self.prev,'state':state,'resume_live_allowed':False})
 def close(self):
  if not self.f.closed:
   try:self.flush()
   finally:self.f.close()

def read_journal(path):
 prev='0'*64;seq=0;session=None
 with Path(path).open('rb') as f:
  while True:
   header=f.read(4)
   if not header:return
   if len(header)!=4:raise ValueError('TORN_HEADER')
   n=struct.unpack('>I',header)[0]
   if n>MAX_RECORD+65536:raise ValueError('INVALID_FRAME_SIZE')
   h=f.read(32);compressed=f.read(n)
   if len(h)!=32 or len(compressed)!=n:raise ValueError('TORN_FRAME')
   try:
    d=zlib.decompressobj();raw=d.decompress(compressed,MAX_RECORD+1)
    if len(raw)>MAX_RECORD or not d.eof or d.unused_data:raise ValueError('INVALID_COMPRESSION')
    if hashlib.sha256(raw).digest()!=h:raise ValueError('HASH_MISMATCH')
    row=json.loads(raw)
   except (zlib.error,json.JSONDecodeError) as e:raise ValueError('CORRUPT_FRAME') from e
   if session is None:session=row['session']
   if row['session']!=session or row['seq']!=seq or row['previous']!=prev:raise ValueError('CHAIN_MISMATCH')
   prev=h.hex();seq+=1;yield row

def recover(path):
 count=0;checkpoint=None;last=None
 for row in read_journal(path):
  if row['bucket']=='CHECKPOINT':
   p=row['payload']
   if p['previous_seq']!=row['seq']-1 or p['previous_hash']!=row['previous']:raise ValueError('CHECKPOINT_LINK_MISMATCH')
   checkpoint=row
  count+=1;last=row
 return {'complete_prefix':True,'records':count,'last_checkpoint':checkpoint,'last_record':last,'live_resume_allowed':False,'admissible_24h':False}

class BookCapture:
 def __init__(self,journal):self.journal=journal;self.states={};self.signatures={};self.generation=0;self.normalizer=None;self.latest=None
 def activate(self,slug,condition,tokens,expiry):
  from app.collectors.polymarket_ws import PolymarketOrderbookCollector
  if not slug or not condition or set(tokens)!= {'UP','DOWN'} or len(set(tokens.values()))!=2:raise ValueError('IDENTITY_REQUIRED')
  self.generation+=1;self.states={};self.signatures={};self.latest=None
  fields={'market_slug':slug,'condition_id':condition,'token_up':tokens['UP'],'token_down':tokens['DOWN'],'generation':self.generation}
  identity=types.SimpleNamespace(fields=lambda:fields)
  self.normalizer=PolymarketOrderbookCollector('5m',tokens,None,expiry_ts_ms=expiry,identity=identity,timestamp_contract='D5.1');self.normalizer._connection_generation=self.generation
  self.journal.append('CONTROL',{'kind':'ACTIVATE_OR_ROTATE','identity':fields,'expiry_ts_ms':expiry})
 def ingest(self,payload,received):
  if self.normalizer is None:raise ValueError('NO_ACTIVE_MARKET')
  raw_seq=self.journal.append('RAW',{'kind':'POLYMARKET','receive_ts_ms':received,'generation':self.generation,'payload':payload})
  events=payload if isinstance(payload,list) else [payload]
  for ev in events:
   ev=self.normalizer._unwrap_event(ev) if isinstance(ev,dict) else {}
   t=ev.get('timestamp',ev.get('event_ts_ms'))
   if t is not None and int(t)>received:raise ValueError('FUTURE_SOURCE_TIMESTAMP')
  snap=self.normalizer.normalize_snapshot(payload,received)
  if not snap or 'up' not in snap or 'down' not in snap:return None
  for side in ('up','down'):
   q=snap[side];token=q['token_id']
   if token not in self.normalizer._initialized_tokens:continue
   signature=digest(q)
   if signature!=self.signatures.get(token):
    state_id=f'{self.journal.session}:{self.journal.seq}:{token}'
    self.journal.append('BOOK_META',{'kind':'BOOK_STATE','state_id':state_id,'raw_seq':raw_seq,'generation':self.generation,'token':token,'market':snap.get('condition_id'),'slug':snap.get('market_slug'),'source_ts_ms':q.get('event_ts_ms'),'receive_ts_ms':q.get('received_ts_ms',received),'view_sha256':signature,'full_depth_sha256':digest(self.normalizer._books[token]),'depth_encoding':'Replay referenced RAW sequence with sealed normalizer; full raw levels preserved, original V1 view remains top20'})
    self.states[token]=state_id;self.signatures[token]=signature
  snap['_causal_states']=self.states.copy();snap['_raw_seq']=raw_seq;self.latest=snap;return snap
 def full_depth(self,token):return copy.deepcopy(self.normalizer._books[token])

class Fixed25Ledger:
 """Historical FIXED25 arithmetic only; technical fills, no net-edge verdict."""
 def __init__(self,keep_results=True):self.capital=500.;self.portfolios={'fixed_25':types.SimpleNamespace(capital=500.)};self.results=[];self.keep_results=keep_results
 def sizes(self,available):return {'fixed_25':min(25,available)}
 def record_signal(self,row):pass
 def record_skip(self,row):
  if self.keep_results:self.results.append(('SKIP',copy.deepcopy(row)))
 def record_fill(self,name,row,pnl):
  self.capital+=float(pnl);self.portfolios[name].capital=self.capital
  if self.keep_results:self.results.append(('FILL',copy.deepcopy(row)))
 def snapshot(self,*args,**kwargs):pass

class Observer:
 def __init__(self,journal,clock):self.journal=journal;self.clock=clock;self.current=None;self.last_tick=None;self.opportunities={};self.phase=None;self.last_clock=None
 def __call__(self,kind,payload):
  if kind=='BOOK':return
  now=self.clock();p=copy.deepcopy(payload)
  if self.last_clock is not None and now<self.last_clock:raise ValueError('DECISION_CLOCK_REGRESSION')
  self.last_clock=now
  if kind=='BTC':
   tick=p['tick'];self.last_tick={'source_ts_ms':getattr(tick,'event_ts_ms',None),'receive_ts_ms':tick.recv_ts_ms,'price':tick.price}
   return
  if kind=='BOOK':return
  signal=p.get('signal_ts')
  if signal is not None:
   self.current=f'{self.journal.session}:signal:{signal}'
  if kind=='SIGNAL':p.update(signal_source_ts=self.last_tick.get('source_ts_ms') if self.last_tick else None,signal_receive_ts=signal,signal_decision_ts=now)
  if kind=='ENTRY_INTENT':p['entry_due_ts']=now+250
  if kind=='EXIT_WAIT':p['exit_due_ts']=now+500
  if kind in ('ENTRY_BOOK','EXIT_BOOK'):
   snap=p.pop('snapshot');side=p['side'].lower();q=snap.get(side,{}) if snap else {};token=q.get('token_id');prefix='entry' if kind=='ENTRY_BOOK' else 'exit'
   state=(snap.get('_causal_states',{}) if snap else {}).get(token)
   p.update({f'actual_{prefix}_observation_ts':now,f'actual_{prefix}_book_state_id':state,f'{prefix}_book_source_ts':q.get('event_ts_ms'),f'{prefix}_book_receive_ts':q.get('received_ts_ms'),f'{prefix}_book_sequence':int(state.split(':')[1]) if state else None,'snapshot_raw_sequence':snap.get('_raw_seq') if snap else None,'market':snap.get('condition_id') if snap else None,'slug':snap.get('market_slug') if snap else None,'token':token,'full_depth_reference':state,'selected_v1_view_sha256':digest(q)})
   if q.get('received_ts_ms',0)>now:raise ValueError('FUTURE_DECISION_BOOK')
  if kind in ('ENTRY_CALC','EXIT_CALC'):self.phase=kind
  if kind=='FILL_LEVEL':p['phase']=self.phase
  if kind=='ENTRY_CALC':self.opportunities[self.current]={'budget':p['budget'],'shares':0.}
  if kind=='ENTRY_RESULT':
   state=self.opportunities.setdefault(self.current,{})
   state['shares']=p['shares'];p['unspent_budget']=state.get('budget',0)-p['cost'];p['entry_residual_shares']=p['shares']
  if kind=='EXIT_BOOK' and self.opportunities.get(self.current,{}).get('shares',0)==0:self.opportunities.pop(self.current,None)
  if kind=='EXIT_RESULT':p['exit_residual_shares']=p['remaining'];self.opportunities.pop(self.current,None)
  if kind=='SKIP':p['residual_shares']=self.opportunities.get(self.current,{}).get('shares',0.);self.opportunities.pop(self.current,None)
  self.journal.append('CAUSAL',{'kind':kind,'opportunity_id':self.current,'decision_ts_ms':now,'fee_policy_reference':'MARKET_FEE_UNQUALIFIED','simulated_context':'taker; FIXED25; no order','payload':p})

def instrumentation_tree(source):
 tree=observed_tree(source)
 for node in ast.walk(tree):
  if isinstance(node,ast.AsyncFunctionDef) and node.name=='execute_signal':
   new=[]
   for stmt in node.body:
    if ast.unparse(stmt)=='await asyncio.sleep(a.hold_ms / 1000)':new.append(ast.parse('_prospective_observe("EXIT_WAIT",dict(signal_ts=signal_ts,side=side))').body[0])
    new.append(stmt)
   node.body=new
 return ast.fix_missing_locations(tree)

def build_v1(root,journal,ledger,latest,clock=None,sleep=None,instrumented=True):
 source=(Path(root)/'analysis/run_d6_paper_live.py').read_text();tree=instrumentation_tree(source) if instrumented else ast.parse(source)
 if instrumented and ast.dump(strip_observations(tree),include_attributes=False)!=ast.dump(ast.parse(source),include_attributes=False):raise ValueError('ECONOMIC_AST_CHANGED')
 observer=Observer(journal,clock or (lambda:time.time_ns()//1000000))
 names=('fill','liquidate','execute_signal','on_btc','on_quote')
 functions=[copy.deepcopy(n) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
 wrapper=ast.parse('def bind():\n last_signal=-10**18\n return None').body[0]
 wrapper.body[-1:]=functions+[ast.parse('return dict(execute_signal=execute_signal,on_btc=on_btc,on_quote=on_quote)').body[0]]
 pending=set();failures=[]
 def supervise(coro):
  task=asyncio.create_task(coro)
  def done(t):
   if not t.cancelled() and t.exception() is not None:failures.append(t.exception())
  task.add_done_callback(done);return task
 env={'a':types.SimpleNamespace(latency_ms=250,hold_ms=500),'ledger':ledger,'latest':latest,'btc':deque(maxlen=4096),'pending':pending,'dryrun':None,'staged':None,'asyncio':types.SimpleNamespace(sleep=sleep or asyncio.sleep,create_task=supervise),'_prospective_observe':observer}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'<CAUSAL_CAPTURE_V1_R2>','exec'),env)
 result=env['bind']();result.update(pending=pending,failures=failures,observer=observer,ast_sha256=hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest());return result


def reconstruct_state(path,state_id,before_sequence=None):
 """Bounded read-only reconstruction of a decision's full depth from canonical RAW."""
 class Sink:
  session='reconstruction';seq=0
  def append(self,*args,**kwargs):self.seq+=1;return self.seq-1
 b=BookCapture(Sink());raw_seq=None;snap=None
 for row in read_journal(path):
  p=row['payload']
  if before_sequence is not None and row['seq']>=before_sequence:break
  if row['bucket']=='CONTROL' and p.get('kind')=='ACTIVATE_OR_ROTATE':
   i=p['identity'];b.activate(i['market_slug'],i['condition_id'],{'UP':i['token_up'],'DOWN':i['token_down']},p['expiry_ts_ms'])
  elif row['bucket']=='RAW' and p.get('kind')=='POLYMARKET':
   raw_seq=row['seq'];snap=b.ingest(p['payload'],p['receive_ts_ms'])
  elif row['bucket']=='BOOK_META' and p['state_id']==state_id:
   if snap is None or p['raw_seq']!=raw_seq or p['generation']!=b.generation:raise ValueError('STATE_LINK_INVALID')
   q=next((snap[k] for k in ('up','down') if snap[k]['token_id']==p['token']),None)
   depth=b.full_depth(p['token'])
   if digest(q)!=p['view_sha256'] or digest(depth)!=p['full_depth_sha256']:raise ValueError('STATE_CONTENT_INVALID')
   return {'state_id':state_id,'sequence':row['seq'],'metadata':p,'full_depth':depth,'v1_view':q}
 raise ValueError('STATE_NOT_OBSERVABLE_BEFORE_DECISION')
