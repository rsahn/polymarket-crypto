"""Preparation-only 24 h protocol. No collector, economic evaluator or real dataset loader."""
from pathlib import Path
from decimal import Decimal, ROUND_CEILING
import json
from analysis.d6.prospective_v1.core import PartitionPlan, Seal, AccessGate, write_once, safety, file_hash
VERSION='BTC_V1_24H_INITIAL_QUALIFICATION_V1'
HOURS=(12,6,6)
EMBARGO_MS=60000
RATE=Decimal('254621.285030')
REQUIRED_SOURCE_PROOFS=('continuous_24h','clock_qualified','complete_event_order','full_depth',
 'token_market_generation','actual_entry_state','actual_exit_state','signal_observation',
 'entry_due','decision_clocks','reconstruction_match','source_hash_verified')
def plan(start_ms):
 if type(start_ms) is not int or start_ms<0:raise ValueError('INVALID_START')
 return PartitionPlan(start_ms,tuple(h*3600000 for h in HOURS),EMBARGO_MS)
def boundaries(start_ms):
 p=plan(start_ms);lo=p.start;out={}
 for name,duration in zip(('TRAIN','VALIDATION','OOS'),p.durations):
  out[name]={'start_ms':lo,'end_ms':lo+duration,'eligible_from_ms':lo+(0 if name=='TRAIN' else p.embargo)};lo+=duration
 return out
def source_reasons(evidence):
 return [k for k in REQUIRED_SOURCE_PROOFS if evidence.get(k) is not True]
def sample_feasibility(criteria):
 result={}
 for split,hours in zip(('TRAIN','VALIDATION','OOS'),HOURS):
  causes=[]
  if hours//6<criteria['active_6h_blocks_min']:causes.append('ACTIVE_6H_BLOCKS_IMPOSSIBLE')
  for key in ('block_hours','sensitivity_block_hours'):
   if hours<2*criteria['confidence'][key]:causes.append('INSUFFICIENT_'+key.upper())
  result[split]={'hours':hours,'max_active_6h_blocks':hours//6,'verdict':'INCONCLUSIVE_INSUFFICIENT_SAMPLE' if causes else 'NOT_EVALUATED','reasons':causes}
 return result
def storage(free_bytes,journal=None,checkpoint=None,scratch=None):
 values=(free_bytes,journal,checkpoint,scratch)
 if any(v is not None and (type(v) is not int or v<0) for v in values):raise ValueError('INVALID_BYTE_BOUND')
 if free_bytes is None:raise ValueError('FREE_SPACE_REQUIRED')
 archive=int((RATE*86400).to_integral_value(rounding=ROUND_CEILING))
 known=all(v is not None for v in (journal,checkpoint,scratch))
 subtotal=archive+journal+checkpoint+scratch if known else None
 margin=int((Decimal(subtotal)*Decimal('.2')).to_integral_value(rounding=ROUND_CEILING)) if known else None
 total=subtotal+margin if known else None
 return dict(ARCHIVE_24H_BYTES=archive,JOURNAL_24H_BOUND=journal,CHECKPOINT_24H_BOUND=checkpoint,SCRATCH_REQUIREMENT=scratch,ENGINEERING_MARGIN=margin,ENGINEERING_MARGIN_POLICY='20 percent of all qualified components, rounded up',QUALIFIED_24H_REQUIRED_SPACE=total,CURRENT_FREE_SPACE=free_bytes,ADDITIONAL_SPACE_REQUIRED=max(0,total-free_bytes) if known else None,status='STORAGE_24H_QUALIFIED' if known and total<=free_bytes else 'STORAGE_24H_UNQUALIFIED')
def replay_status(evidence):
 required=('full_event_mix','record_size_bound','active_positions_bound','runtime_24h_bound','scratch_24h_bound','restart_qualified','causal_binding_qualified')
 missing=[k for k in required if evidence.get(k) is not True]
 return {'status':'REPLAY_24H_UNQUALIFIED' if missing else 'STREAMING_REPLAY_24H_QUALIFIED','missing':missing}
def prepare(directory,root):
 """Freeze preparation artifacts exclusively. Unbound fields deliberately block execution."""
 safety();directory=Path(directory);directory.mkdir(exist_ok=False,parents=True);root=Path(root)
 names=['analysis/d6/paper_live.py','analysis/run_d6_paper_live.py',
        'analysis/d6/prospective_24h_v1/criteria.json','analysis/d6/prospective_24h_v1/PROTOCOL.json',
        'analysis/d6/prospective_24h_v1/protocol.py','analysis/d6/prospective_v1/core.py']
 seal=Seal.create(root,names)
 manifest={'protocol_version':VERSION,'hours':list(HOURS),'total_hours':24,'embargo_ms':EMBARGO_MS,
  'purpose':'INITIAL_MICROLIVE_QUALIFICATION','NOT_LONG_HORIZON_STABILITY_PROOF':True,
  'strategy_hashes':{n:seal.hashes[n] for n in names[:2]},'preparation_runner_hash':seal.hashes[names[4]],
  'runner_hash':None,'criteria_hash':seal.hashes[names[2]],'ledger_version':seal.hashes[names[5]],
  'fee_policy_version':None,'depth_policy_version':None,'partition_boundaries':None,
  'dataset_identity':None,'collector_identity':None,'T0':None,'status':'PREPARATION_ONLY_UNBOUND',
  'real_partition_loader_enabled':False,**safety()}
 write_once(directory/'MANIFEST.json',manifest)
 write_once(directory/'PREPARATION_SEAL.json',{'hashes':seal.hashes,'seal_hash':seal.hash,'manifest_sha256':file_hash(directory/'MANIFEST.json')})
 return manifest

def verify_preparation(directory,root):
 directory=Path(directory);s=json.loads((directory/'PREPARATION_SEAL.json').read_text());seal=Seal(s['hashes']);seal.verify(root)
 if seal.hash!=s['seal_hash'] or file_hash(directory/'MANIFEST.json')!=s['manifest_sha256']:raise ValueError('MANIFEST_CHANGED')
 return json.loads((directory/'MANIFEST.json').read_text())
