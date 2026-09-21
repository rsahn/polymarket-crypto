"""User-authorized early stop; no database access until collector exits."""
import ctypes,datetime,json,os,pathlib,subprocess,sys,time,traceback
from console_stop import interrupt_console
ROOT=pathlib.Path(__file__).resolve().parents[3]
HERE=pathlib.Path(__file__).resolve().parent
STATUS=ROOT/'analysis/d5/24h_20260920_124822/status.json'
DB=ROOT/'data/d5_24h_20260920_085530/d5_live_24h_20260920_124822.db'
OUT=ROOT/'analysis/d5/3h_20260920_124822_review'
SESSION='83b5cc8a-4592-4676-b28d-3da2ac6d0088'
TARGET_SECONDS=10920
PID=4920
LAUNCHER=13112
state={'pid':os.getpid(),'collector_pid':PID,'session_id':SESSION,'target_seconds':TARGET_SECONDS,'minimum_review_seconds':10800,'database':str(DB),'review_output':str(OUT),'research_allowed':False,'mode':'SHADOW','strategy':'NO_TRADE','capital':500}
def update(**changes):
    state.update(changes);state['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    temp=HERE/'controller_status.tmp';temp.write_text(json.dumps(state,indent=2),encoding='utf-8');temp.replace(HERE/'controller_status.json')
def main():
    fd=os.open(HERE/'controller.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];k.OpenProcess.restype=ctypes.c_void_p
    k.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong];k.WaitForSingleObject.restype=ctypes.c_ulong
    k.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=k.OpenProcess(0x100000,False,PID)
    if not handle:raise OSError('Cannot hold collector process handle')
    awake=bool(k.SetThreadExecutionState(0x80000001))
    try:
        update(phase='WAITING_FOR_3H_2M',started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        while True:
            s=json.loads(STATUS.read_text(encoding='utf-8'))
            if s.get('pid')!=PID or s.get('session_id')!=SESSION or s.get('database')!=str(DB):raise RuntimeError('Collector identity changed')
            if s.get('phase')!='COLLECTING':raise RuntimeError('Collector no longer collecting before planned stop')
            if k.WaitForSingleObject(handle,0)!=258:raise RuntimeError('Collector already exited')
            age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(s['updated_utc'])).total_seconds()
            if age>300:raise RuntimeError('Collector status stale; no blind signal')
            elapsed=s['elapsed_seconds'];update(last_observed_elapsed_seconds=elapsed,free_bytes=s.get('free_bytes'))
            if elapsed>=TARGET_SECONDS:break
            time.sleep(min(15,max(1,TARGET_SECONDS-elapsed)))
        # Validate full console scope immediately before the only interrupt.
        scope=interrupt_console(PID,{PID,LAUNCHER},send=False)
        update(phase='STOP_SIGNAL_AUTHORIZED',console_scope=scope,reason='USER_REVISED_24H_TO_3H_STORAGE_RISK',signal_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        interrupt_console(PID,{PID,LAUNCHER},send=True)
        update(phase='WAITING_FOR_CLEANUP',signal_sent=True)
        if k.WaitForSingleObject(handle,120000)!=0:raise RuntimeError('Collector did not exit after Ctrl+C; no force kill attempted')
        update(phase='COLLECTOR_EXITED',collector_status_raw=json.loads(STATUS.read_text(encoding='utf-8')))
        # Writer is closed before imports/review. Do not rewrite its FAILED/KeyboardInterrupt status.
        OUT.mkdir(exist_ok=False)
        (OUT/'USER_STOP_CONTEXT.json').write_text(json.dumps({'user_authorized_target':'3 hours usable; 120-second acquisition margin','signal':'Windows CTRL_C_EVENT','session_status_may_be_failed':'prospective/live mark interruption FAILED; preserve original evidence','original_24h_protocol_not_passed':True,'minimum_seconds':10800,'stop_controller':state},indent=2),encoding='utf-8')
        sys.path.insert(0,str(ROOT/'backend'))
        from app.d5.prospective import clock_snapshot
        (OUT/'clock_after_user_stop.json').write_text(json.dumps(clock_snapshot(),indent=2),encoding='utf-8')
        from app.d5.quality import review
        from app.d5.store import code_version
        update(phase='DATA_QUALITY')
        def progress(changes):update(**changes)
        report=review(DB,OUT,SESSION,minimum_seconds=10800,progress=progress,final_code_version=code_version())
        update(phase='REVIEW_READY' if report['QUALITY_REVIEW_PASSED'] else 'QUALITY_REVIEW_BLOCKED',quality_passed=report['QUALITY_REVIEW_PASSED'],quality_failures=report['QUALITY_FAILURES'],replay_hashes_equal=report['REPLAY_HASHES_EQUAL'],final_report=str(OUT/'FINAL_DATA_QUALITY_REPORT.md'))
    finally:
        k.CloseHandle(handle)
        if awake:k.SetThreadExecutionState(0x80000000)
if __name__=='__main__':
    try:main()
    except BaseException as exc:
        update(phase='CONTROLLER_FAILED',error=repr(exc),traceback=traceback.format_exc())
        raise
