"""Public-only bootstrap or foreground persistent cursor worker. Never readiness."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from contextlib import contextmanager
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from app.live.collateral_onchain import PublicRPC,validate_rpc_endpoint
from app.live.genesis_ledger import read_genesis,expected_wallet
from app.live.inventory_catchup import CatchupRPC,catch_up,CatchupBlocked
from analysis.qualify_post_genesis import load_inventory_cursor
from analysis.qualify_post_b_proofs import qualify_finalized
from app.live.deposit_qualification import write_report
from app.live.post_c_completeness import current_inventory_diagnostic

@contextmanager
def worker_lock(root):
 folder=root/'runtime/d6_inventory_cursors';folder.mkdir(parents=True,exist_ok=True)
 with (folder/'worker.lock').open('a+b') as f:
  if f.tell()==0:f.write(b'0');f.flush()
  f.seek(0)
  if os.name=='nt':
   import msvcrt
   msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
  else:
   import fcntl
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:yield
  finally:
   if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(f,fcntl.LOCK_UN)

def cycle(root,endpoint):
 path=root/'runtime/d6_genesis.db';before=hashlib.sha256(path.read_bytes()).hexdigest()
 prior=read_genesis(path);rpc=None
 report=dict(mode='BOOTSTRAP_CATCHUP',status='BLOCKED',SYSTEM_READY=False,ready_for_arm=False,submit_allowed=False,
  current_inventory_proven=False,inventory_through_C_proven=False,private_key_loaded=False,credentials_loaded=False,
  post_C_completeness='NO_COMMON_POST_C_COMPLETENESS_WATERMARK')
 try:
  if prior['phase']!='GENESIS_RECONCILED' or prior['event_count']!=0 or prior['snapshot']['wallet'].lower()!=expected_wallet().lower():raise CatchupBlocked('GENESIS_BINDING_OR_RECOVERY_REQUIRED')
  cursor=load_inventory_cursor(root,prior)
  rpc=PublicRPC(expected_wallet(),endpoint=endpoint,allow_finalized=True,pooled=True);rpc.log_window=10
  paced=CatchupRPC(rpc);paced.begin_tranche()
  qualified=qualify_finalized(paced)
  report.update(catch_up(paced,prior,cursor,qualified['anchor'],root=root),finalized=qualified)
 except Exception as exc:
  safe={'INVENTORY_CURSOR_REQUIRED','CURSOR_INTEGRITY','CURSOR_CONFLICT','FINALIZED_UNPROVEN'}
  category=exc.category if isinstance(exc,CatchupBlocked) else exc.args[0] if exc.args and isinstance(exc.args[0],str) and exc.args[0] in safe else 'BOOTSTRAP_CONFIGURATION_OR_EVIDENCE_FAILURE'
  report['TAIL_SCAN_ROOT_CAUSE']=category
 finally:
  report['rpc_calls']=rpc.calls if rpc else []
  if rpc:rpc.close()
  report['genesis_unchanged']=hashlib.sha256(path.read_bytes()).hexdigest()==before
  if not report['genesis_unchanged']:report.update(status='BLOCKED',inventory_through_C_proven=False,TAIL_SCAN_ROOT_CAUSE='GENESIS_CHANGED_DURING_CATCHUP')
 report['current_inventory_proof']=current_inventory_diagnostic(catchup=report)
 return report

def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--bootstrap',action='store_true');g.add_argument('--watch',action='store_true')
 p.add_argument('--poll-seconds',type=float);args=p.parse_args()
 if args.watch and (args.poll_seconds is None or not 0<args.poll_seconds<86400):p.error('--watch requires an explicit bounded --poll-seconds')
 if args.bootstrap and args.poll_seconds is not None:p.error('--poll-seconds is for --watch')
 flags={k:os.getenv(k,'false').strip().lower() for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')}
 if any(v!='false' for v in flags.values()):print('FLAGS_FALSE_REQUIRED');return 2
 try:endpoint=validate_rpc_endpoint(os.getenv('POLYGON_ARCHIVE_RPC_URL'))
 except ValueError:print('POLYGON_ARCHIVE_RPC_URL_NOT_CONFIGURED_OR_INVALID');return 2
 try:
  with worker_lock(ROOT):
   while True:
    report=cycle(ROOT,endpoint);report['flags']=flags
    output=ROOT/('D6_INVENTORY_CATCHUP_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    write_report(output,report)
    print(json.dumps({k:report.get(k) for k in ('status','TAIL_SCAN_ROOT_CAUSE','cursor_start','cursor_end','backlog_blocks','inventory_through_C_proven','current_inventory_proven')},sort_keys=True),flush=True)
    print('REPORT_FILE='+output.name,flush=True)
    if report['status']!='PASS_SCOPED_CATCHUP':return 1
    if args.bootstrap:return 0
    time.sleep(args.poll_seconds)
 except KeyboardInterrupt:print('STOPPED_LAST_COMPLETE_CHECKPOINT_PRESERVED');return 130
 except OSError:print('WORKER_LOCK_OR_LOCAL_IO_BLOCKED');return 1

if __name__=='__main__':raise SystemExit(main())
