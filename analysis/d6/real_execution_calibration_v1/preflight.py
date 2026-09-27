"""Read-only preparation preflight. Never arms or creates an SDK client."""
import json,hashlib,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from analysis.d6.real_execution_calibration_v1.v1_binding import verify
REQUIRED=('wallet_account_identity_verified','balance_sufficient','market_identity_verified','sdk_order_path_qualified','account_evidence_adapter_qualified','fee_upper_bound_proven','exit_handoff_ready','ledger_healthy','kill_switch_tested','reconciliation_tested','clock_sanity','ws_healthy','tests_green','audit_pass')
STORAGE_REQUIRED=512*1024**2

def evaluate(evidence,now_ms,free_bytes,verifier=None):
 from analysis.d6.real_execution_calibration_v1.qualification import inspect_evidence
 hashes=verify();details={}
 for k in REQUIRED:
  try:
   if verifier is None:raise ValueError('INDEPENDENT_VERIFIER_REQUIRED')
   if verifier.context['strategy_hashes']!=hashes:raise ValueError('EVIDENCE_CODE_MISMATCH')
   verifier.validate(k,evidence.get(k),now_ms);details[k]=None
  except (ValueError,KeyError,TypeError,ArithmeticError) as exc:details[k]=str(exc)
 checks={k:details[k] is None for k in REQUIRED}
 checks['storage_sufficient']=free_bytes>=STORAGE_REQUIRED
 checks['fresh_runtime_evidence']=type(evidence.get('observed_ms')) is int and 0<=now_ms-evidence['observed_ms']<=5000
 checks['global_D6_flags_false']=all(__import__('os').environ.get(k,'false').lower()=='false' for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED'))
 failures=sorted(k for k,v in checks.items() if not v)
 return {'kind':'REAL_EXECUTION_CALIBRATION_PREFLIGHT','status':'CALIBRATION_BLOCKED' if failures else 'CALIBRATION_READY','checks':checks,'evidence_failures':details,'blockers':failures,'strategy_hashes':hashes,'budget_caps':{'entry':25,'total_including_fee_reservations':100,'entry_attempts':4,'open_positions':1},'storage':{'required_bytes':STORAGE_REQUIRED,'free_bytes':free_bytes,'journal_max_bytes':256*1024**2,'reports_max_bytes':64*1024**2,'recovery_bytes':64*1024**2,'margin_bytes':128*1024**2},'evaluated_ms':now_ms,'armed':False,'SYSTEM_READY':False,'current_inventory_proven':False,'submit_allowed':False}

if __name__=='__main__':
 print(json.dumps(evaluate({},time.time_ns()//1000000,shutil.disk_usage(ROOT).free),indent=2))
