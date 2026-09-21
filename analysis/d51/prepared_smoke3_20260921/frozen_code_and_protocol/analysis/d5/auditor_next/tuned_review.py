"""Full D5 review via auditor_next and unchanged quality.review; fail closed, source read-only."""
import pathlib,sys,json,time,datetime,os,sqlite3,types,hashlib,argparse
from acceleration import build_projection,replay_database,ROOT
from audit_next import audit
from run_accelerated import process_alive
from app.d5 import quality
from app.d5.store import code_version
from sqlite_tuning import connect_ro,CACHE_KIB

NAMES=['Preparation metadata','Audit_next complet','SQLite integrity_check source','SQLite foreign_key_check source','Qualite / provenance source','Replay NoTrade 1 source','Replay NoTrade 2 source','Comparaison et quality gate']
def run(source,out,session,budget=3600,minimum=10800,reuse_review=None):
 source=pathlib.Path(source).resolve();out=pathlib.Path(out).resolve();out.mkdir(exist_ok=False,parents=True)
 started=time.monotonic();before=(source.stat().st_size,source.stat().st_mtime_ns);stage_start=[started];last=[0.];current=[0];total=[None];completed=[]
 state={'pid':os.getpid(),'status':'RUNNING','steps_total':8,'research_allowed':False,'paper_started':False,'source':str(source),'minimum_seconds':minimum,'alert_after_seconds':budget,'hard_timeout':False,'sqlite_cache_kib':CACHE_KIB}
 def save(path,data):
  text=json.dumps(data,ensure_ascii=False,indent=2);tmp=path.with_suffix('.tmp');tmp.write_text(text,encoding='utf-8')
  for attempt in range(12):
   try:tmp.replace(path);return
   except PermissionError:time.sleep(.02*(attempt+1))
  path.write_text(text,encoding='utf-8')
 def pulse(extra=None,force=False):
  now=time.monotonic()
  state['one_hour_alert']=now-started>budget
  state.update(extra or {});state.update(elapsed_seconds=now-started,stage_elapsed_seconds=now-stage_start[0],updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),completed_steps=list(completed))
  if not force and now-last[0]<1:return
  last[0]=now;save(out/'progress.json',state)
  with (out/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(state,ensure_ascii=False)+'\n')
 def begin(n):
  current[0]=n;stage_start[0]=time.monotonic();pulse({'step':n,'stage':NAMES[n-1],'rows_processed':None,'total_rows':None,'percent':None,'rows_per_second':None,'detail':None,'sql':None},True)
 def finish(ok,details=None):
  completed.append({'step':current[0],'stage':NAMES[current[0]-1],'status':'PASS' if ok else 'FAIL','seconds':time.monotonic()-stage_start[0],'details':details});pulse(force=True)
 stream=[None,0.]
 def callback(info=None):
  info=info or {};rows=info.get('rows_processed',info.get('rows',info.get('events_replayed')));count=info.get('total_rows',info.get('total'))
  if info.get('event')=='heartbeat' or info.get('step') in ('sqlite_work','index'):rows=count=None
  key=(current[0],info.get('table'),info.get('stage'))
  if rows is not None and key!=stream[0]:stream[:]=[key,time.monotonic()]
  fields={'detail':info,'rows_processed':rows,'total_rows':count,'percent':100*rows/count if rows is not None and count else None,'rows_per_second':rows/max(.001,time.monotonic()-stream[1]) if rows is not None else None}
  if info.get('sql'):fields['sql']=info['sql']
  pulse(fields,force=info.get('event') in ('start','complete'))
 def audit_call(path,sid):
  if reuse_review is not None:
   prior=pathlib.Path(reuse_review).resolve();m=json.loads((prior/'RUN_MANIFEST.json').read_text(encoding='utf-8'));p=json.loads((prior/'progress.json').read_text(encoding='utf-8'));report=json.loads((prior/'AUDIT_NEXT_REPORT.json').read_text(encoding='utf-8'))
   checks=[pathlib.Path(m['source']).resolve()==source,list(before)==m['source_stat_before'],report['SESSION']['session_id']==sid,m['quality_sha256']==hashlib.sha256(pathlib.Path(quality.__file__).read_bytes()).hexdigest()]
   for filename in ('acceleration.py','audit_next.py'):
    checks.append(m['code_files'][filename]==hashlib.sha256((pathlib.Path(__file__).parent/filename).read_bytes()).hexdigest())
   for n in (1,2):checks.append(any(x.get('step')==n and x.get('status')=='PASS' for x in p['completed_steps']))
   if not all(checks):raise RuntimeError('PRIOR_COMPLETED_AUDIT_PROVENANCE_MISMATCH')
   for n in (1,2):
    begin(n);finish(True,{'carried_forward_completed_step':True,'prior_review':str(prior),'note':'User authorized completion of missing checks; no historical PID12408 result reused'})
   total[0]=report['TOTAL_EVENTS'];quality.write_new(out/'AUDIT_NEXT_REPORT.json',report)
   quality.write_new(out/'CARRIED_AUDIT_PROVENANCE.json',{'prior_review':str(prior),'report_sha256':hashlib.sha256((prior/'AUDIT_NEXT_REPORT.json').read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256((prior/'RUN_MANIFEST.json').read_bytes()).hexdigest(),'checks':checks})
   return report
  begin(1);projection=out/'metadata_projection.db';build_projection(path,projection,callback);finish(True,{'note':'Derived metadata only; not integrity or replay evidence'})
  begin(2);report=audit(projection,sid,callback);total[0]=report['TOTAL_EVENTS'];quality.write_new(out/'AUDIT_NEXT_REPORT.json',report)
  failures=[v for v in report['SMOKE_FAILURES'] if v!='RECONNECT_NOT_OBSERVED'];finish(not failures,{'failures':failures})
  if failures:raise RuntimeError('AUDIT_NEXT_FAILED:'+str(failures))
  return report
 class Connection(sqlite3.Connection):
  def execute(self,sql,parameters=()):
   normalized=sql.strip().lower()
   if normalized in ('pragma integrity_check','pragma foreign_key_check'):
    number=3 if normalized.endswith('integrity_check') else 4;begin(number);pulse({'sql':sql},True);rows=list(super().execute(sql,parameters));okay=rows==[('ok',)] if number==3 else not rows
    quality.write_new(out/('INTEGRITY_CHECK.json' if number==3 else 'FOREIGN_KEY_CHECK.json'),rows);finish(okay,rows)
    if not okay:raise RuntimeError('SOURCE_SQLITE_CHECK_FAILED:'+normalized)
    return iter(rows)
   if current[0]==4:begin(5)
   pulse({'sql':sql,'rows_processed':None,'total_rows':None,'percent':None,'rows_per_second':None})
   return super().execute(sql,parameters)
 def connect(*args,**kwargs):
  if not args or 'mode=ro' not in str(args[0]):raise RuntimeError('SOURCE_CONNECTION_MUST_BE_READ_ONLY')
  kwargs['factory']=Connection;c=connect_ro(*args,**kwargs)
  def progress_sql():pulse();return 0
  c.set_progress_handler(progress_sql,100000);return c
 replay_number=[0]
 def replay_call(*args,**kwargs):
  if current[0]==5:finish(True,{'note':'All quality metrics computed; policy evaluated at final gate'})
  replay_number[0]+=1;begin(5+replay_number[0]);sink=kwargs.get('decision_sink');count=[0]
  def tracked(record):
   count[0]+=1
   if sink:sink(record)
   if count[0]%1000==0:pulse({'rows_processed':count[0],'total_rows':total[0],'percent':100*count[0]/total[0],'rows_per_second':count[0]/max(.001,time.monotonic()-stage_start[0])})
  kwargs['decision_sink']=tracked
  opened=[]
  def replay_connect(*a,**k):
   c=connect_ro(*a,**k);opened.append(c);return c
  rg=dict(replay_database.__globals__);rg['sqlite3']=types.SimpleNamespace(connect=replay_connect,Row=sqlite3.Row)
  tuned_replay=types.FunctionType(replay_database.__code__,rg,'replay_database',replay_database.__defaults__)
  try:result=tuned_replay(*args,**kwargs)
  finally:
   for c in opened:c.close()
  m=result['metrics'];ok=count[0]==total[0] and m['number_of_orders']==0 and m['number_of_fills']==0 and m['final_cash']==500 and not any(m[k] for k in ('paired_qty','directional_up','directional_down'))
  finish(ok,{'events':count[0],'no_trade':ok})
  if not ok:
   quality.write_new(out/f'REPLAY_{replay_number[0]}_FAILED_RESULT.json',{'event_count':count[0],'result':result,'result_sha256':hashlib.sha256(quality.encode(result).encode()).hexdigest()})
   raise RuntimeError('REPLAY_INCOMPLETE_OR_NOT_INERT')
  return result
 def gate(report,replay_ok,minimum_seconds):
  begin(8);failures=quality.quality_gate(report,replay_ok,minimum_seconds)
  if before!=(source.stat().st_size,source.stat().st_mtime_ns):failures.append('SOURCE_CHANGED_DURING_REVIEW')
  finish(not failures,{'failures':failures});return failures
 namespace=dict(quality.review.__globals__);namespace.update(audit=audit_call,sqlite3=types.SimpleNamespace(connect=connect),replay_database=replay_call,quality_gate=gate)
 review=types.FunctionType(quality.review.__code__,namespace,'review',quality.review.__defaults__);review.__kwdefaults__=quality.review.__kwdefaults__.copy()
 save(out/'RUN_MANIFEST.json',{'source':str(source),'source_stat_before':before,'prior_completed_audit':str(reuse_review) if reuse_review else None,'new_source_integrity_fk_and_replays':True,'alert_only_seconds':budget,'cache_kib':CACHE_KIB,'quality_sha256':hashlib.sha256(pathlib.Path(quality.__file__).read_bytes()).hexdigest(),'code_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path(__file__).parent.glob('*.py')},'source_integrity_fk_and_two_replays':True,'old_audit_disposition':'OLD_AUDIT_ABORTED_BY_USER_FOR_PERFORMANCE'})
 try:
  report=review(source,out,session,minimum_seconds=minimum,progress=lambda _:None,final_code_version=code_version())
  state.update(status='COMPLETE',D5_DATA_QUALITY='PASS' if report['QUALITY_REVIEW_PASSED'] else 'FAIL');pulse(force=True);save(out/'VERDICT.json',{'D5_DATA_QUALITY':state['D5_DATA_QUALITY'],'duration_seconds':time.monotonic()-started,'failures':report['QUALITY_FAILURES'],'replays':report['REPLAYS'],'source_stat_unchanged':before==(source.stat().st_size,source.stat().st_mtime_ns)})
  return report
 except BaseException as exc:
  if not completed or completed[-1]['step']!=current[0]:completed.append({'step':current[0],'status':'FAIL','error':repr(exc)})
  state.update(status='FAILED',D5_DATA_QUALITY='FAIL',error=repr(exc),elapsed_seconds=time.monotonic()-started,stage_elapsed_seconds=time.monotonic()-stage_start[0],updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),completed_steps=completed);save(out/'progress.json',state);save(out/'VERDICT.json',{'D5_DATA_QUALITY':'FAIL','duration_seconds':time.monotonic()-started,'failures':[repr(exc)],'replay_hashes':'Only completed REPLAY_N.json are evidence; not fabricated for unexecuted steps'});raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--db',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--session',required=True);p.add_argument('--reuse-review',type=pathlib.Path);p.add_argument('--alert-seconds',type=int,default=3600);a=p.parse_args()
 if process_alive(12408) or process_alive(10548):raise RuntimeError('PREVIOUS_AUDIT_STILL_ALIVE')
 run(a.db,a.out,a.session,budget=a.alert_seconds,reuse_review=a.reuse_review)
