"""Candidate full-chain runner. Never interrupts another process. Explicit execution flag required."""
import argparse,ctypes,datetime,hashlib,json,pathlib,sqlite3,sys,time,types
from ctypes import wintypes as w
from acceleration import compact_audit,replay_database,ROOT
from app.d5 import quality
from app.d5.store import code_version

def process_alive(pid):
 k=ctypes.WinDLL('kernel32',use_last_error=True)
 k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
 k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.CloseHandle.argtypes=[w.HANDLE]
 h=k.OpenProcess(0x100000,False,pid)
 if not h:
  error=ctypes.get_last_error()
  if error==87:return False
  raise ctypes.WinError(error)
 try:return k.WaitForSingleObject(h,0)==258
 finally:k.CloseHandle(h)

def run(db,out,session,budget_seconds=3600,minimum_seconds=10800):
 out=pathlib.Path(out).resolve();db=pathlib.Path(db).resolve()
 if out==db or out in db.parents:raise ValueError('Output must be separate from source')
 if out.exists():raise FileExistsError('New output directory required')
 out.mkdir(parents=True,exist_ok=False)
 start=time.monotonic();deadline=start+budget_seconds;last_write=[0]
 state={'phase':'STARTING','research_allowed':False,'target_seconds':budget_seconds,'source':str(db),'session':session}
 source_stat=(db.stat().st_size,db.stat().st_mtime_ns)
 def check():
  if time.monotonic()>=deadline:raise TimeoutError('INCOMPLETE_TIME_BUDGET: no quality validation')
 def update(changes=None,force=False):
  check();state.update(changes or {});now=time.monotonic()
  if not force and now-last_write[0]<1:return
  last_write[0]=now;state['elapsed_seconds']=now-start;state['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  temp=out/'progress.tmp';temp.write_text(json.dumps(state,indent=2),encoding='utf-8');temp.replace(out/'progress.json')
  with (out/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(state)+'\n')
 def connect(*args,**kwargs):
  connection=sqlite3.connect(*args,**kwargs)
  connection.execute('PRAGMA query_only=ON')
  def pulse():
   if time.monotonic()>=deadline:return 1
   update();return 0
  connection.set_progress_handler(pulse,100000)
  connection.set_trace_callback(lambda sql:update({'phase':'QUALITY_SQL','sql':sql},True))
  return connection
 def accelerated_replay(*args,**kwargs):
  sink=kwargs.get('decision_sink');counter=[0]
  def checked_sink(record):
   counter[0]+=1
   if counter[0]%1000==0:check()
   if sink:sink(record)
  kwargs['decision_sink']=checked_sink
  return replay_database(*args,**kwargs)
 namespace=dict(quality.review.__globals__)
 namespace.update(audit=lambda path,sid:compact_audit(path,sid,out/'metadata_projection.db',update),replay_database=accelerated_replay,sqlite3=types.SimpleNamespace(connect=connect))
 review=types.FunctionType(quality.review.__code__,namespace,'review',quality.review.__defaults__)
 review.__kwdefaults__=quality.review.__kwdefaults__.copy()
 manifest={'source_database':str(db),'projection_is_not_dataset':True,'quality_source_sha256':hashlib.sha256(pathlib.Path(quality.__file__).read_bytes()).hexdigest(),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path(__file__).parent.glob('*.py')},'original_integrity_and_foreign_keys':True,'original_db_replayed_twice':True,'minimum_seconds':minimum_seconds,'budget_seconds':budget_seconds}
 (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 try:
  report=review(db,out,session,minimum_seconds=minimum_seconds,progress=update,final_code_version=code_version())
  check()
  if source_stat!=(db.stat().st_size,db.stat().st_mtime_ns):raise RuntimeError('SOURCE_CHANGED_DURING_REVIEW')
  update({'phase':'COMPLETE','quality_passed':report['QUALITY_REVIEW_PASSED'],'failures':report['QUALITY_FAILURES']},True)
  return report
 except BaseException as exc:
  state.update(phase='INCOMPLETE_TIME_BUDGET' if time.monotonic()>=deadline else 'FAILED',error=repr(exc),research_allowed=False,elapsed_seconds=time.monotonic()-start)
  (out/'progress.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
  raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--db',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--session',required=True)
 p.add_argument('--execute-after-authorization',action='store_true');p.add_argument('--budget-seconds',type=int,default=3600)
 args=p.parse_args()
 if not args.execute_after_authorization:p.error('Execution requires explicit authorization; candidate only')
 if process_alive(12408):p.error('Historical audit PID 12408 still alive; refusing duplicate audit')
 if args.budget_seconds<=0:p.error('Positive time budget required')
 run(args.db,args.out,args.session,args.budget_seconds)
if __name__=='__main__':main()
