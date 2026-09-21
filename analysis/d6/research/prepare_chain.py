"""One sequential preparation chain. No audit/collector/Paper launch; derived data only."""
import pathlib,sys,json,time,os,hashlib,subprocess,datetime
HERE=pathlib.Path(__file__).resolve().parent;D6=HERE.parent;ROOT=D6.parents[1]
from offline import execute
from context_join import run as join

def main(data,out):
 out.mkdir(exist_ok=False);started=time.monotonic();status={'pid':os.getpid(),'mode':'PREPARATION_ONLY','paper_started':False,'out':str(out)}
 def update(phase,**extra):
  status.update(phase=phase,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-started,**extra)
  (out/'status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
 files=list((D6/'paper_runtime').glob('*.py'))+list(HERE.glob('*.py'))+[HERE/'SPLIT_LOCK.json']
 frozen={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
 (out/'PRE_ANALYSIS_CODE_LOCK.json').write_text(json.dumps({'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'before_actual_result_analysis':True,'sha256':frozen},indent=2),encoding='utf-8')
 try:
  update('SYNTHETIC_TESTS');tests=[]
  for folder in ('pipeline','paper_runtime','research'):
   command=[sys.executable,'-m','unittest','discover','-s',str(D6/folder),'-p','test_*.py','-v']
   result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
   tests.append({'suite':folder,'returncode':result.returncode,'output':result.stdout+result.stderr})
   (out/'TEST_RESULTS.json').write_text(json.dumps(tests,indent=2),encoding='utf-8')
   if result.returncode:raise RuntimeError('TEST_FAILURE_'+folder)
  while True:
   progress=json.loads((data/'progress.json').read_text(encoding='utf-8'))
   if progress['status']=='COMPLETE':break
   if progress['status']=='FAILED':raise RuntimeError('CONVERSION_FAILED:'+str(progress.get('error')))
   if time.time()-(data/'progress.json').stat().st_mtime>1800:raise RuntimeError('CONVERSION_STATUS_STALE_30MIN')
   update('WAITING_FOR_CONVERSION',conversion_stage=progress.get('stage'),conversion_percent=progress.get('percent'));time.sleep(20)
  update('CONTEXT_JOIN');join(data,out/'context')
  update('OFFLINE_PORTFOLIOS');execute(data,out/'offline')
  current={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
  if current!=frozen:raise RuntimeError('CODE_CHANGED_DURING_PREPARATION_ANALYSIS')
  update('COMPLETE_REQUIRES_REVIEW',code_unchanged=True,oos_opened=False,quality_verdict='NOT_GRANTED',paper_started=False)
 except BaseException as exc:update('FAILED',error=repr(exc));raise
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--data',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();main(a.data.resolve(),a.out.resolve())
