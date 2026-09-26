"""Read-only preparation, resumable at complete canonical tranches only.
Never proves post-C inventory, changes Genesis, or grants readiness.
"""
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid
from .collateral_onchain import CTF
from .ctf_inventory_probe import scan_ctf
from .genesis_ledger import digest

class CatchupBlocked(ValueError):
 def __init__(self,category):self.category=category;super().__init__(category)

class CatchupRPC:
 """Serial, existing 200ms pacing. At most 3 attempts for classified transients.
 120s dispatch budget per complete tranche, never for an entire bootstrap.
 """
 parallel_inventory_reads=False
 def __init__(self,rpc,*,clock=time.monotonic,sleep=time.sleep):
  self.rpc=rpc;self.clock=clock;self.sleep=sleep;self.next_start=clock();self.deadline=None
  self.retries=0;self.rate_limits=0;self.splits=0;self.waited=0.;self.requests=0
 def __getattr__(self,k):return getattr(self.rpc,k)
 def begin_tranche(self):self.deadline=self.clock()+120
 def call(self,m,p):
  for attempt in range(3):
   delay=max(0,self.next_start-self.clock())
   if self.deadline is not None and self.clock()+delay>=self.deadline:raise CatchupBlocked('TRANCHE_DISPATCH_BUDGET_EXCEEDED')
   if delay:self.sleep(delay);self.waited+=delay
   self.next_start=self.clock()+.2;self.requests+=1
   before=len(self.rpc.calls)
   try:return self.rpc.call(m,p)
   except Exception:
    entry=self.rpc.calls[-1] if len(self.rpc.calls)>before else {}
    category=entry.get('error_category','UNCLASSIFIED_READ_ERROR');status=entry.get('http_status')
    allowed={'TIMEOUT','CONNECTION_ERROR','RATE_LIMIT','RANGE_LIMIT','ARCHIVE_UNAVAILABLE','METHOD_UNAVAILABLE','METHOD_UNSUPPORTED','PLAN_RESTRICTION','INVALID_PARAMS','HTTP_ERROR','RESPONSE_TOO_LARGE','RPC_ENVELOPE_INVALID','INVALID_JSON','UNCLASSIFIED_RPC_ERROR','UNCLASSIFIED_READ_ERROR'}
    if category not in allowed:category='UNCLASSIFIED_READ_ERROR'
    limited=status==429 or category=='RATE_LIMIT'
    if limited:self.rate_limits+=1;category='RATE_LIMIT'
    if m=='eth_getLogs' and (category=='RANGE_LIMIT' or status==413):
     q=p[0];lo,hi=int(q['fromBlock'],16),int(q['toBlock'],16)
     if lo<hi:
      mid=(lo+hi)//2;self.splits+=1
      left=self.call(m,[{**q,'toBlock':hex(mid)}]);right=self.call(m,[{**q,'fromBlock':hex(mid+1)}])
      if not isinstance(left,list) or not isinstance(right,list):raise CatchupBlocked('RPC_LOG_SCHEMA')
      return left+right
    transient=limited or category in ('TIMEOUT','CONNECTION_ERROR') or status in (500,502,503,504) and category=='HTTP_ERROR'
    if not transient or attempt==2:raise CatchupBlocked(category) from None
    self.retries+=1;self.next_start=max(self.next_start,self.clock()+.2*(2**attempt))
 def report(self):return dict(rpc_requests=self.requests,retries=self.retries,rate_limits=self.rate_limits,range_splits=self.splits,pacing_wait_ms=self.waited*1000,max_in_flight=1,min_start_interval_ms=200,tranche_dispatch_budget_seconds=120,max_attempts=3)

def verify_header(rpc,n,h=None):
 value=rpc.call('eth_getBlockByNumber',[hex(n),False])
 import re
 if value.get('number')!=hex(n) or not isinstance(value.get('hash'),str) or not re.fullmatch('0x[0-9a-f]{64}',value['hash']):raise CatchupBlocked('HEADER_INVALID')
 if h is not None and value['hash']!=h:raise CatchupBlocked('CURSOR_REORG_OR_CONFLICT')
 return value

def validate_checkpoint(cp,prior):
 try:
  x=cp['inventory_incremental'];e=x['catchup_evidence']
  if not (cp['cursor_schema']==2 and cp['genesis_unchanged'] is True):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (cp['genesis_snapshot_sha256']==prior['snapshot_sha256'] and digest(x)==cp['inventory_sha256']):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (x['status']=='PASS_SCOPED_READS' and x['from_block']==prior['snapshot']['block_number']+1):raise CatchupBlocked('CURSOR_INTEGRITY')
  if e['wallet'].lower()!=prior['snapshot']['wallet'].lower():raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (e['chain_id']==137 and e['contract']==CTF and e['scope']=='CTF_INCOMING_EVENTS_REQUESTED_RANGE_ONLY'):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (e['cursor_hash_verified'] is True and e['canonical_rechecked'] is True):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (type(e['parent_block']) is int and e['parent_block']>=prior['snapshot']['block_number']):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (e['last_complete_range']==[e['parent_block']+1,x['to_block']]):raise CatchupBlocked('CURSOR_INTEGRITY')
  expected=e['parent_block']+1
  for lo,hi in e['ranges']:
   if not (type(lo) is int and type(hi) is int and lo==expected and lo<=hi<=x['to_block']):raise CatchupBlocked('CURSOR_INTEGRITY')
   expected=hi+1
  if not (expected==x['to_block']+1):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (e['boundary_hash']==x['block_hash'] and e['genesis_block_hash']==prior['snapshot']['block_hash']):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (e['parent_inventory_sha256'] and e['parent_hash']):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (x['events_count']==0 and isinstance(x['balances'],dict) and all(isinstance(v,str) and v.isdigit() and int(v)==0 for v in x['balances'].values())):raise CatchupBlocked('CURSOR_INTEGRITY')
  if not (type(x['observed_ms']) is int and e['started_ms']<=x['observed_ms']<=e['finished_ms']):raise CatchupBlocked('CURSOR_INTEGRITY')
 except (KeyError,ValueError,TypeError,AssertionError):raise CatchupBlocked('CURSOR_INTEGRITY') from None
 return x

def publish(root,prior,x):
 cp=dict(cursor_schema=2,genesis_snapshot_sha256=prior['snapshot_sha256'],genesis_unchanged=True,inventory_incremental=x,inventory_sha256=digest(x))
 validate_checkpoint(cp,prior)
 folder=Path(root)/'runtime/d6_inventory_cursors';folder.mkdir(parents=True,exist_ok=True)
 target=folder/(str(x['to_block'])+'_'+uuid.uuid4().hex+'.json')
 fd,tmp=tempfile.mkstemp(dir=folder,suffix='.tmp')
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(cp,f);f.flush();os.fsync(f.fileno())
  os.link(tmp,target)
 finally:os.unlink(tmp)
 return str(target.relative_to(root))

def catch_up(rpc,prior,cursor,target,*,root):
 """Fixed target, 500-block checkpoint tranches, original <=10-block log reads.
 500 is the existing RPC maximum window, not a freshness limit. No total cap.
 Legacy cursors remain a scoped trust anchor, never upgraded to global coverage.
 """
 started=time.monotonic();start=cursor['to_block'];end=target['number'];current=cursor
 window=rpc.log_window
 report=dict(mode='BOOTSTRAP_CATCHUP',status='BLOCKED',cursor_start=start,cursor_end=start,target_boundary=target,backlog_blocks=end-start,
  ranges_planned=math.ceil(max(0,end-start)/window),ranges_completed=0,ranges_failed=0,first_failed_range=None,last_complete_range=None,
  checkpoint_start=digest(cursor),checkpoint_end=digest(cursor),cursor_hash_verified=False,inventory_through_C_proven=False,
  current_inventory_proven=False,post_C_completeness='NO_COMMON_POST_C_COMPLETENESS_WATERMARK',SYSTEM_READY=False,ready_for_arm=False,submit_allowed=False,
  TAIL_SCAN_ROOT_CAUSE=None,checkpoints_written=0,scope='IDENTIFIED_CTF_THROUGH_FIXED_C_NOT_CURRENT')
 active=None
 try:
  if not 1<=window<=10:raise CatchupBlocked('BOOTSTRAP_WINDOW_POLICY')
  if rpc.wallet.lower()!=prior['snapshot']['wallet'].lower():raise CatchupBlocked('CURSOR_WALLET_MISMATCH')
  rpc.begin_tranche()
  if rpc.call('eth_chainId',[])!='0x89':raise CatchupBlocked('CHAIN_MISMATCH')
  verify_header(rpc,start,cursor['block_hash']);report['cursor_hash_verified']=True
  verify_header(rpc,prior['snapshot']['block_number'],prior['snapshot']['block_hash'])
  verify_header(rpc,end,target['hash'])
  if end<start:raise CatchupBlocked('CURSOR_AHEAD_OF_FINALIZED')
  if cursor.get('events_count')!=0 or any(int(v) for v in cursor['balances'].values()):raise CatchupBlocked('RECOVERY_REQUIRED')
  while current['to_block']<end:
   lo=current['to_block']+1;hi=min(lo+499,end);active=[lo,hi];rpc.begin_tranche()
   verify_header(rpc,current['to_block'],current['block_hash'])
   boundary=verify_header(rpc,hi,target['hash'] if hi==end else None)
   captured={};stamp=time.time_ns()//1000000
   result=scan_ctf(rpc,lo,hi,set(current['balances']),capture=captured)
   d=result.get('diagnostics',{})
   if result['status']!='PASS_SCOPED_READS':
    report['first_failed_range']=d.get('first_failed_range') or active
    raise CatchupBlocked(d.get('cause') or 'CTF_EVIDENCE_INVALID_OR_RPC_FAILED')
   if result['block_hash']!=boundary['hash']:raise CatchupBlocked('BOUNDARY_REORG')
   verify_header(rpc,current['to_block'],current['block_hash'])
   verify_header(rpc,hi,boundary['hash'])
   if result['events_count'] or any(int(v) for v in captured['balances'].values()):raise CatchupBlocked('RECOVERY_REQUIRED')
   ranges=d['ranges_completed'];expected=lo
   for a,b in ranges:
    if a!=expected or b<a or b>hi:raise CatchupBlocked('COVERAGE_GAP_OR_OVERLAP')
    expected=b+1
   if expected!=hi+1:raise CatchupBlocked('COVERAGE_GAP_OR_OVERLAP')
   evidence=dict(chain_id=137,wallet=rpc.wallet,contract=CTF,scope=result['scope'],parent_block=current['to_block'],parent_hash=current['block_hash'],parent_inventory_sha256=digest(current),
    cursor_hash_verified=True,canonical_rechecked=True,genesis_block_hash=prior['snapshot']['block_hash'],boundary_hash=boundary['hash'],last_complete_range=active,
    ranges=ranges,started_ms=stamp,finished_ms=time.time_ns()//1000000)
   value={**result,'from_block':cursor['from_block'],'balances':captured['balances'],'observed_ms':stamp,'catchup_evidence':evidence,'provenance':'RESUMABLE_CANONICAL_CTF_PREPARATION'}
   path=publish(root,prior,value)
   current=value;report.update(cursor_end=hi,checkpoint_end=digest(value),last_complete_range=active,last_checkpoint=path,checkpoints_written=report['checkpoints_written']+1,
    ranges_completed=report['ranges_completed']+len(ranges))
  verify_header(rpc,end,target['hash'])
  report.update(status='PASS_SCOPED_CATCHUP',inventory_through_C_proven=True)
 except Exception as exc:
  category=exc.category if isinstance(exc,CatchupBlocked) else 'CATCHUP_LOCAL_OR_EVIDENCE_FAILURE'
  report.update(TAIL_SCAN_ROOT_CAUSE=category,ranges_failed=1 if active else 0,first_failed_range=report['first_failed_range'] or active)
 finally:
  wall=(time.monotonic()-started)*1000
  latencies=sorted(c['elapsed_ms'] for c in rpc.calls if isinstance(c.get('elapsed_ms'),(int,float)))
  report.update(rpc.report(),wall_ms=wall,blocks_per_second=(report['cursor_end']-start)/(wall/1000) if wall else None,
   ranges_per_second=report['ranges_completed']/(wall/1000) if wall else None,rpc_latency_samples=len(latencies),
   rpc_latency_p50_ms=latencies[len(latencies)//2] if latencies else None,rpc_latency_p95_ms=latencies[min(len(latencies)-1,math.ceil(.95*len(latencies))-1)] if len(latencies)>=20 else None)
 return report
