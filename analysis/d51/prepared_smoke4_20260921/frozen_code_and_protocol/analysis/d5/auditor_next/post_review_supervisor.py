"""Serial post-review provenance and timestamp checks. Never signals another process."""
import argparse,json,pathlib,time,datetime,os,hashlib
from atomic_status import write_status
from verify_source_provenance import verify
from timestamp_supplement import run as timestamp_audit
from run_accelerated import process_alive

def main(review,reference):
 review=pathlib.Path(review).resolve();reference=pathlib.Path(reference).resolve();checkpoint=review/'post_review_progress.json'
 if checkpoint.exists():
  old=json.loads(checkpoint.read_text())
  if old.get('status')=='RUNNING' and process_alive(old['pid']):raise RuntimeError('Post-review supervisor already active')
  raise FileExistsError('Preserve existing post-review execution; diagnose before retry')
 start=time.monotonic();status={'pid':os.getpid(),'status':'RUNNING','source_writes':False,'research_allowed':False,'paper_started':False}
 def update(phase,**extra):
  status.update(extra,phase=phase,elapsed_seconds=time.monotonic()-start,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());write_status(checkpoint,status)
 update('WAITING_FOR_CORE_REVIEW_EXIT')
 try:
  while True:
   core=json.loads((review/'progress.json').read_text(encoding='utf-8'));alive=process_alive(core['pid'])
   update('WAITING_FOR_CORE_REVIEW_EXIT',core_pid=core['pid'],core_step=core.get('step'),core_alive=alive)
   if not alive:break
   time.sleep(15)
  if core['status']=='RUNNING':raise RuntimeError('CORE_EXITED_WITHOUT_TERMINAL_STATUS')
  if core['status']=='FAILED':raise RuntimeError('CORE_TOOL_FAILURE_REQUIRES_AUTOMATIC_DIAGNOSIS')
  update('FULL_SOURCE_SHA256')
  attestation=verify(review,reference)
  if attestation['status']!='PASS':raise RuntimeError('SOURCE_OR_CODE_PROVENANCE_FAILURE')
  update('ACCEPTED_TIMESTAMPS_AND_GAPS')
  supplement=timestamp_audit(review)
  update('COMPLETE_RESULT_COMPARISON')
  r=json.loads((review/'FINAL_DATA_QUALITY_REPORT.json').read_text());a=json.loads((review/'REPLAY_1.json').read_text());b=json.loads((review/'REPLAY_2.json').read_text())
  comparison={k:a[k]==b[k] for k in ('event_count','decision_sha256','result_sha256','result')}
  failures=list(r['QUALITY_FAILURES'])
  if not all(comparison.values()):failures.append('INDEPENDENT_FINAL_REPLAY_COMPARISON_FAILED')
  for key,value in supplement['timestamp_checks'].items():
   if value['previous_regressions']:failures.append('ACCEPTED_TIMESTAMP_REGRESSION_'+key)
  if supplement['accepted_available_regressions']:failures.append('ACCEPTED_AVAILABLE_REGRESSIONS')
  for key in ('source_stat_unchanged','coverage_matches','feed_gaps_equal_quality'):
   if not supplement[key]:failures.append('SUPPLEMENT_'+key.upper())
  final={'D5_DATA_QUALITY':'FAIL' if failures else 'PASS','quality_failures':sorted(set(failures)),'core_quality_failures':r['QUALITY_FAILURES'],'replay_comparison':comparison,'replays':r['REPLAYS'],'source_sha256':attestation['source_sha256'],'source_and_code_provenance':attestation['status'],'timestamp_supplement_complete':True,'core_duration_seconds':json.loads((review/'VERDICT.json').read_text())['duration_seconds'],'post_supervisor_seconds_including_wait':time.monotonic()-start,'source_hash_seconds':attestation['duration_seconds'],'timestamp_supplement_seconds':supplement['duration_seconds'],'dataset_label':'prospective D5 short-window dataset, not 24h validation','research_allowed':False,'paper_started':False,'required_next_action':'Diagnose quality findings before user escalation; distinguish tool errors and data defects' if failures else 'D5 checks complete; supervisor must inspect all evidence before D6'}
  with (review/'SUPERVISOR_D5_VERDICT.json').open('x') as f:json.dump(final,f,indent=2)
  update('SUPPLEMENTS_COMPLETE',status='COMPLETE',D5_DATA_QUALITY=final['D5_DATA_QUALITY'])
 except BaseException as exc:update('AUTOMATIC_DIAGNOSIS_REQUIRED',status='ERROR',error=repr(exc));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--review',type=pathlib.Path,required=True);p.add_argument('--reference',type=pathlib.Path,required=True);a=p.parse_args();main(a.review,a.reference)
