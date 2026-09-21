"""D5.1 only: new SHADOW smoke, then full optimized read-only review."""
import argparse,asyncio,datetime,hashlib,json,os,pathlib,shutil,signal,sqlite3,sys,time,types
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'analysis/d5/auditor_next'))
from app.d5.clock51 import snapshot
from app.d5.protocol51 import ntp_gate
from app.d5.live import run as collect_live
from app.d5.store import code_version
from app.d5.quality51 import supplement,gate
from atomic_status import write_status as atomic_json
import tuned_review
from contextlib import closing


def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def write_new(path,data):
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False)


def review(source,out,sid,clock_samples,minimum=1200):
    """Reuse optimized instrumented execution, with explicitly separate D5.1 gate."""
    before=(source.stat().st_size,source.stat().st_mtime_ns)
    def prospective_gate(report,replay_ok,minimum_seconds):
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            s=supplement(db,sid,report['SESSION']['started_at_ms'],report['COLLECTION_STOP_TS_MS'],progress=lambda info:atomic_json(out/'supplement_progress.json',dict(info,updated_utc=utc())))
        write_new(out/'D51_SUPPLEMENT.json',s)
        return gate(report,replay_ok,minimum_seconds,s,clock_samples)
    q=tuned_review.quality
    proxy=types.SimpleNamespace(**{n:getattr(q,n) for n in ('__file__','review','write_new','encode')},quality_gate=prospective_gate)
    env=dict(tuned_review.run.__globals__);env['quality']=proxy
    execute=types.FunctionType(tuned_review.run.__code__,env,'run',tuned_review.run.__defaults__)
    result=execute(source,out,sid,minimum=minimum)
    digest=sha(source)
    stable=before==(source.stat().st_size,source.stat().st_mtime_ns)
    failures=list(result['QUALITY_FAILURES'])
    if not stable:failures.append('SOURCE_CHANGED_DURING_HASH')
    final=dict(protocol='D5.1',historical_D5_DATA_QUALITY='FAIL',D51_DATA_QUALITY='FAIL' if failures else 'PASS',failures=failures,
        source_sha256=digest,source_stat_unchanged=stable,smoke_only=True,statistical_D6_validation=False,
        research_allowed=False,paper_started=False,replays=result['REPLAYS'],report=result,
        gap_policy='D5.1 QUALITY_PROTOCOL.md: verified transitions <=10s; internal/reconnect <=5s; endpoints <=10s')
    write_new(out/'D51_FINAL_REPORT.json',final)
    (out/'D51_FINAL_REPORT.md').write_text('# D5.1 instrumentation smoke\n\n'+json.dumps({k:v for k,v in final.items() if k!='report'},indent=2)+'\n\nLegacy-format FINAL_DATA_QUALITY_REPORT.md is an intermediate metrics rendering; its legacy gap-policy prose does not describe D5.1. This separate report and frozen protocol are authoritative for this new experiment only.\n',encoding='utf-8')
    return final


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=1320);p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
    if a.seconds<1320:raise ValueError('At least 1320 seconds requested for >=1200 useful seconds')
    if shutil.disk_usage(ROOT).free<10*1024**3:raise RuntimeError('Need 5 GiB reserve plus 5 GiB smoke budget')
    tag=datetime.datetime.now().strftime('%Y%m%d_%H%M%S');out=ROOT/'analysis/d51'/('smoke_'+tag);out.mkdir(exist_ok=False)
    dbdir=ROOT/'data/d51';dbdir.mkdir(exist_ok=True);db=dbdir/('d51_smoke_'+tag+'.db')
    state=dict(pid=os.getpid(),phase='PREFLIGHT',mode='SHADOW',strategy='NO_TRADE',capital=500,orders=0,fills=0,inventory=0,paper_started=False,research_allowed=False,database=str(db),started_utc=utc())
    def update(extra):state.update(extra);state['updated_utc']=utc();atomic_json(out/'status.json',state)
    clocks=[]
    def clock(phase):
        item=snapshot();item['phase']=phase;clocks.append(item);write_new(out/('clock_'+phase+'_'+str(time.time_ns())+'.json'),item);return ntp_gate(item)
    awake=False
    try:
        if os.name=='nt':
            import ctypes
            awake=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            if not awake:raise OSError('Unable to keep host awake')
        update(dict(keep_awake=awake))
        failures=clock('gate_1')
        if failures:raise RuntimeError('CLOCK_PREFLIGHT_FAILED:'+str(failures))
        time.sleep(30)
        failures=clock('gate_2')
        if failures:raise RuntimeError('CLOCK_PREFLIGHT_FAILED:'+str(failures))
        frozen=dict(code_version=code_version(),requested_seconds=a.seconds,protocol_hashes={x.name:sha(x) for x in (ROOT/'analysis/d51').glob('*.md')},created_utc=utc())
        write_new(out/'LAUNCH_MANIFEST.json',frozen)
        if a.prepare_only:update(dict(phase='PREFLIGHT_PASS_NO_COLLECTION'));return
        # WriterCore owns creation of the SQLite database and deliberately refuses
        # pre-existing paths. Reserve uniqueness via the smoke directory/tag only;
        # do not pre-create the DB here.
        if db.exists():
            raise FileExistsError(f'Smoke database path unexpectedly exists: {db}')
        async def collect():
            stop=asyncio.Event();loop=asyncio.get_running_loop()
            def request_stop(*_):loop.call_soon_threadsafe(stop.set)
            previous=signal.signal(signal.SIGINT,request_stop)
            async def ntp_monitor():
                while True:
                    await asyncio.sleep(300)
                    problems=await asyncio.to_thread(clock,'during')
                    update(dict(last_clock_failures=problems))
            monitor=asyncio.create_task(ntp_monitor())
            try:return await collect_live(types.SimpleNamespace(db=db,seconds=a.seconds,reconnect_after=0,compress_payloads=True,min_free_bytes=5*1024**3,on_progress=update,timestamp_contract='D5.1',stop_event=stop))
            finally:
                monitor.cancel();await asyncio.gather(monitor,return_exceptions=True);signal.signal(signal.SIGINT,previous)
        update(dict(phase='COLLECTING'));collected=asyncio.run(collect());write_new(out/'COLLECTION_RESULT.json',collected)
        clock('after');update(dict(phase='AUDITING',collection=collected))
        result=review(db,out/'review',collected['session_id'],clocks)
        update(dict(phase='COMPLETE',D51_DATA_QUALITY=result['D51_DATA_QUALITY'],failures=result['failures']))
    except BaseException as exc:
        update(dict(phase='FAILED',error=repr(exc)));raise
    finally:
        if awake:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            update(dict(keep_awake=False))

if __name__=='__main__':main()
