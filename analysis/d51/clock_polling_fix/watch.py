import pathlib,sys,json,time,datetime,os
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from app.d5.clock51 import snapshot
from app.d5.protocol51 import ntp_gate
OUT=pathlib.Path(__file__).resolve().parent
state=dict(pid=os.getpid(),phase='OBSERVING',started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),samples=[])
start=time.monotonic()
while True:
    s=snapshot();stamp=time.time_ns();(OUT/f'watch_{stamp}.json').write_text(json.dumps(s,indent=2),encoding='utf-8')
    state['samples'].append(dict(file=f'watch_{stamp}.json',failures=ntp_gate(s),w32time=s['w32time']))
    state['elapsed_seconds']=time.monotonic()-start;state['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if state['elapsed_seconds']>=1200:state['phase']='COMPLETE'
    (OUT/'watch_status.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    if state['phase']=='COMPLETE':break
    time.sleep(120)
