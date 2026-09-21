"""Local read-only dashboard; explicit fixed routes only, no trading controls."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pathlib,json
HERE=pathlib.Path(__file__).resolve().parent;D6=HERE.parent;ROOT=D6.parents[1]
def conversion_status():
 active=read(D6/'pipeline/active.json');folder=pathlib.Path(active.get('output',str(D6/'data'))).resolve()
 if D6.resolve() not in folder.parents:return {}
 return read(folder/'progress.json')
def read(path):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except (OSError,ValueError):return {}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path=='/':body=(HERE/'dashboard.html').read_bytes();mime='text/html; charset=utf-8'
  elif self.path=='/api/status':
   body=json.dumps({'paper':read(D6/'paper_status.json'),'verdict':read(D6/'OFFLINE_VERDICT.json'),'conversion':conversion_status(),'audit':read(ROOT/'analysis/d5/audit_progress_monitor/progress.json')}).encode();mime='application/json'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8766),Handler).serve_forever()
