"""Read-only SDK transport inspection before wiring real submission.

Prints method signatures only. It never creates, signs, posts, cancels, or submits orders.
"""
import asyncio,inspect,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))

def load_env():
 p=ROOT/".env"
 if not p.exists():return
 for raw in p.read_text(encoding="utf-8-sig").splitlines():
  line=raw.strip()
  if not line or line.startswith("#") or "=" not in line:continue
  k,v=line.split("=",1);k=k.strip();v=v.strip()
  if len(v)>=2 and v[0]==v[-1] and v[0] in ("'",'"'):v=v[1:-1]
  os.environ.setdefault(k,v)

async def main():
 load_env()
 from polymarket import AsyncSecureClient
 key=os.getenv("SIGNER_PRIVATE_KEY")
 if not key:raise RuntimeError("SIGNER_PRIVATE_KEY missing")
 client=await AsyncSecureClient.create(private_key=key)
 try:
  names=("create_limit_order","place_limit_order","place_market_order","post_order",
         "post_orders","get_order","get_orders","get_trades","cancel_order",
         "cancel_orders","cancel_all")
  for name in names:
   fn=getattr(client,name,None)
   print(f"{name}: {inspect.signature(fn) if fn else 'MISSING'}")
 finally:
  await client.close()

if __name__=="__main__":
 asyncio.run(main())
