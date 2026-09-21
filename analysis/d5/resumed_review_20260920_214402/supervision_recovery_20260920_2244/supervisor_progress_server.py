"""Read-only process telemetry and live display. Never opens the D5 database."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import ctypes,datetime,json,os,threading,time
from ctypes import wintypes as w
ROOT=Path(__file__).resolve().parents[3]
k=ctypes.WinDLL('kernel32',use_last_error=True)
class IO(ctypes.Structure):
 _fields_=[(n,ctypes.c_ulonglong) for n in ('read_operations','write_operations','other_operations','read_bytes','write_bytes','other_bytes')]
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.GetProcessIoCounters.argtypes=[w.HANDLE,ctypes.POINTER(IO)];k.GetProcessTimes.argtypes=[w.HANDLE,*[ctypes.POINTER(w.FILETIME)]*4];k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.CloseHandle.argtypes=[w.HANDLE]
def proc(pid):
 h=k.OpenProcess(0x1000|0x100000,False,pid)
 if not h:
  error=ctypes.get_last_error()
  return {'pid':pid,'alive':False if error==87 else None,'error_code':error}
 try:
  io=IO();ts=[w.FILETIME() for _ in range(4)]
  if not k.GetProcessIoCounters(h,ctypes.byref(io)) or not k.GetProcessTimes(h,*[ctypes.byref(t) for t in ts]):raise ctypes.WinError(ctypes.get_last_error())
  cpu=sum((t.dwHighDateTime<<32)+t.dwLowDateTime for t in ts[2:])/1e7
  created=((ts[0].dwHighDateTime<<32)+ts[0].dwLowDateTime)/1e7-11644473600
  return {'pid':pid,'alive':k.WaitForSingleObject(h,0)==258,'cpu_seconds':cpu,'created_unix':created,**{n:getattr(io,n) for n,_ in IO._fields_}}
 finally:k.CloseHandle(h)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def atomic(p,data):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 for n in range(10):
  try:tmp.replace(p);return
  except PermissionError:time.sleep(.02*(n+1))
 raise PermissionError(str(p))
latest={};guard=threading.Lock()
def monitor():
 previous=None
 while True:
  try:
   pointer=read(ROOT/'analysis/d5/active_review.json');out=Path(pointer['out']);s=read(out/'progress.json');now=datetime.datetime.now(datetime.timezone.utc);mono=time.monotonic();p=proc(s['pid'])
   expected=datetime.datetime.fromisoformat(pointer['started_utc']).timestamp()
   if p.get('created_unix') and abs(p['created_unix']-expected)>60:p={'pid':s['pid'],'alive':False,'identity_mismatch':True}
   s['post_review']=read(out/'post_review_progress.json') if (out/'post_review_progress.json').exists() else {}
   s['hash_progress']=read(out/'hash_progress.json') if (out/'hash_progress.json').exists() else {}
   s['supplement_progress']=read(out/'supplement_progress.json') if (out/'supplement_progress.json').exists() else {}
   s['active_process_role']='core'
   if s['status']!='RUNNING' and s['post_review'].get('status')=='RUNNING' and s['post_review'].get('phase')!='WAITING_FOR_CORE_REVIEW_EXIT':
    p=proc(s['post_review']['pid']);s['active_process_role']='post_review'
   if previous and p.get('alive') and previous[1].get('created_unix')==p.get('created_unix'):
    dt=mono-previous[0]
    for key in ('read_bytes','write_bytes','cpu_seconds'):p[key+'_per_second']=(p[key]-previous[1][key])/dt
   previous=(mono,p.copy())
   heartbeat=datetime.datetime.fromisoformat(s['updated_utc']);s.update(heartbeat_age_seconds=max(0,(now-heartbeat).total_seconds()),monitor_updated_utc=now.isoformat(),monitor_pid=os.getpid(),process=p,progress_last_updated_utc=s['updated_utc'])
   s['source_hash_status']=read(out/'SOURCE_HASH_VERIFICATION.json') if (out/'SOURCE_HASH_VERIFICATION.json').exists() else {'status':'PENDING','note':'Completed audit reuse is provisional until source SHA-256 verification'}
   for c in s.get('completed_steps',[]):
    d=c.get('details') or {}
    if d.get('carried_forward_completed_step'):
     old=read(Path(d['prior_review'])/'progress.json');original=next((x for x in old['completed_steps'] if x.get('step')==c['step']),{})
     c['original_seconds']=original.get('seconds');c['display_status']='PASS precedent / provenance SHA en attente' if s['source_hash_status'].get('status')!='PASS' else 'PASS precedent / provenance verifiee'
   with guard:latest.clear();latest.update(s)
   row={'monitor_updated_utc':now.isoformat(),'step':s.get('step'),'stage':s.get('stage'),'sql':s.get('sql'),'duration_seconds':s.get('elapsed_seconds'),'heartbeat_age_seconds':s['heartbeat_age_seconds'],'process':p,'rows_processed':s.get('rows_processed'),'total_rows':s.get('total_rows'),'status':s.get('status')}
   atomic(out/'telemetry.json',row)
   with (out/'telemetry.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
  except Exception as exc:
   with guard:latest['monitor_error']=repr(exc)
  time.sleep(15)
PAGE='''<!doctype html><meta charset="utf-8"><title>D5 — Supervision qualité</title><style>body{background:#101820;color:#edf3fa;font:17px system-ui;max-width:1050px;margin:35px auto;padding:0 20px}.box{background:#1b2936;padding:20px;border-radius:12px;margin:15px 0}td{padding:10px}small{color:#9bb4c9}pre{white-space:pre-wrap;font-size:13px}progress{width:100%;height:20px}</style><h1>D5 — Supervision qualité</h1><small>Collecte ~3 h 02 · Source immuable · Paper non démarré · Alerte de durée sans coupure</small><div class="box" id="main">Chargement…</div><div class="box" id="telemetry"></div><div class="box"><table id="steps"></table></div><pre id="detail"></pre><script>
const fmt=n=>n==null||!Number.isFinite(Number(n))?'Non mesurable':Number(n).toLocaleString('fr-FR',{maximumFractionDigits:1});
function line(el,text,tag='p'){let p=document.createElement(tag);p.textContent=text;el.append(p)}
async function tick(){try{let s=await(await fetch('/status',{cache:'no-store'})).json();main.replaceChildren();line(main,`Étape ${s.step}/8 — ${s.stage}`,'h2');line(main,`${s.status} · Reprise ${fmt(s.elapsed_seconds/60)} min · Étape ${fmt(s.stage_elapsed_seconds/60)} min`);line(main,`Sous-étape : ${s.sql||s.detail?.stage||s.detail?.step||s.stage}`);line(main,`Lignes : ${fmt(s.rows_processed)} / ${fmt(s.total_rows)} · ${fmt(s.rows_per_second)} lignes/s`);if(s.percent!=null){let p=document.createElement('progress');p.max=100;p.value=s.percent;main.append(p)}if(s.one_hour_alert)line(main,'ALERTE : plus d’une heure ; le contrôle continue sans interruption.');line(main,`Provenance source : ${s.source_hash_status?.status||'PENDING'}`);if(s.post_review?.phase)line(main,`Compléments : ${s.post_review.status} — ${s.post_review.phase}`);if(s.hash_progress?.status==='RUNNING')line(main,`SHA source : ${fmt(s.hash_progress.bytes_processed/1e9)} / ${fmt(s.hash_progress.total_bytes/1e9)} Go · ${fmt(s.hash_progress.bytes_per_second/1e6)} Mo/s`);if(s.supplement_progress?.status==='RUNNING')line(main,`Timestamps/gaps : ${fmt(s.supplement_progress.rows_processed)} / ${fmt(s.supplement_progress.total_rows)} lignes · ${fmt(s.supplement_progress.rows_per_second)} lignes/s`);telemetry.replaceChildren();let p=s.process||{};line(telemetry,`PID ${p.pid} (${s.active_process_role}) · Vivant : ${p.alive} · CPU cumulé ${fmt(p.cpu_seconds)} s · ${fmt(p.cpu_seconds_per_second*100)} % d’un cœur`);line(telemetry,`Lectures ${fmt(p.read_bytes/1e9)} Go · ${fmt(p.read_bytes_per_second/1e6)} Mo/s · Écritures ${fmt(p.write_bytes/1e9)} Go`);line(telemetry,`Heartbeat audit : ${s.progress_last_updated_utc} (âge ${fmt(s.heartbeat_age_seconds)} s)`);line(telemetry,`Relevé externe : ${s.monitor_updated_utc}`);line(telemetry,'I/O processus inclut le cache OS ; aucune conversion fictive en lignes auditées.','small');steps.replaceChildren();for(let c of s.completed_steps||[]){let tr=document.createElement('tr');for(let v of [c.step,c.stage,c.display_status||c.status,fmt(c.original_seconds??c.seconds)+' s']){let td=document.createElement('td');td.textContent=v;tr.append(td)}steps.append(tr)}detail.textContent=JSON.stringify({detail:s.detail,error:s.error,monitor_error:s.monitor_error},null,2)}catch(e){main.textContent=String(e)}}tick();setInterval(tick,2000);
</script>'''
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/status':
   with guard:data=json.dumps(latest,ensure_ascii=False).encode()
   kind='application/json'
  elif self.path=='/':data=PAGE.encode();kind='text/html; charset=utf-8'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
if __name__=='__main__':
 threading.Thread(target=monitor,daemon=True).start();ThreadingHTTPServer(('127.0.0.1',8767),Handler).serve_forever()
