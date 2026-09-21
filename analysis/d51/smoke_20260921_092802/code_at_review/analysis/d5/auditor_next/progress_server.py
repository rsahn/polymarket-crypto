"""Read-only local display of the active D5 validation. No database access."""
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[3]
PAGE='''<!doctype html><meta charset="utf-8"><title>D5 — Revue qualité</title><style>body{background:#101820;color:#edf3fa;font:18px system-ui;max-width:1000px;margin:50px auto}h1{font-size:30px}.box{background:#1b2936;padding:24px;border-radius:12px;margin:18px 0}td,th{padding:10px;text-align:left}small{color:#99b1c7}progress{width:100%;height:20px}pre{white-space:pre-wrap;font-size:13px}</style><h1>D5 — Nouvelle revue qualité</h1><small>Source en lecture seule · Aucun D6 / Paper · Ancien audit abandonné sur décision utilisateur</small><div class="box" id="main">Chargement…</div><div class="box"><table id="steps"></table></div><pre id="detail"></pre><script>
const fmt=n=>n==null?'Non mesurable':Number(n).toLocaleString('fr-FR',{maximumFractionDigits:1});
async function tick(){try{let s=await(await fetch('/status',{cache:'no-store'})).json();main.replaceChildren();let h=document.createElement('h2');h.textContent=`Étape ${s.step}/8 — ${s.stage}`;main.append(h);let p=document.createElement('p');p.textContent=`${s.status} · Total ${fmt(s.elapsed_seconds/60)} min · Étape ${fmt(s.stage_elapsed_seconds/60)} min`;main.append(p);let r=document.createElement('p');r.textContent=`Lignes : ${fmt(s.rows_processed)} / ${fmt(s.total_rows)} · Débit : ${fmt(s.rows_per_second)} lignes/s`;main.append(r);if(s.percent!=null){let b=document.createElement('progress');b.max=100;b.value=s.percent;main.append(b)}let u=document.createElement('small');u.textContent=`Dernière mise à jour : ${s.updated_utc}`;main.append(u);steps.replaceChildren();for(let c of s.completed_steps||[]){let tr=document.createElement('tr');for(let v of [c.step,c.stage,c.status,fmt(c.seconds)+' s']){let td=document.createElement('td');td.textContent=v;tr.append(td)}steps.append(tr)}detail.textContent=JSON.stringify({detail:s.detail,sql:s.sql,error:s.error},null,2)}catch(e){main.textContent='Lecture du statut : '+e}}tick();setInterval(tick,1000);
</script>'''
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  try:
   if self.path=='/status':
    pointer=json.loads((ROOT/'analysis/d5/active_review.json').read_text(encoding='utf-8-sig'));data=(Path(pointer['out'])/'progress.json').read_bytes();kind='application/json'
   elif self.path=='/':data=PAGE.encode();kind='text/html; charset=utf-8'
   else:self.send_error(404);return
   self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
  except Exception:self.send_error(503)
 def log_message(self,*args):pass
HTTPServer(('127.0.0.1',8767),Handler).serve_forever()
