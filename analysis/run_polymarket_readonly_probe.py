import asyncio,json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
def load_local_env():
 p=ROOT/".env"
 if not p.exists(): return
 for raw in p.read_text(encoding="utf-8").splitlines():
  line=raw.strip()
  if not line or line.startswith("#") or "=" not in line: continue
  k,v=line.split("=",1)
  os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
load_local_env()
from app.live.polymarket_readonly import PolymarketReadOnly
async def run():
 p=PolymarketReadOnly()
 try:print(json.dumps(await p.connect(),indent=2))
 finally:await p.close()
if __name__=="__main__":asyncio.run(run())
