"""One-shot live smoke runner.

Default behavior is PREVIEW ONLY. It cannot submit unless the user explicitly
passes --execute AND the independent live-arm environment gates are satisfied.
It submits at most one BUY order and never loops overnight.
"""
from __future__ import annotations
import argparse,asyncio,json,os,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.collectors.polymarket import PolymarketMarketDiscovery
from app.live.clob_staged import StagedClobExecutor
from app.live.real_scaffold import LiveArmConfig,LiveArmGate
from app.live.clob_transport import LiveClobTransport

def load_env():
 p=ROOT/".env"
 if not p.exists():return
 for raw in p.read_text(encoding="utf-8-sig").splitlines():
  line=raw.strip()
  if not line or line.startswith("#") or "=" not in line:continue
  k,v=line.split("=",1);k=k.strip();v=v.strip()
  if len(v)>=2 and v[0]==v[-1] and v[0] in ("'",'"'):v=v[1:-1]
  os.environ.setdefault(k,v)

def geoblock():
 req=urllib.request.Request("https://polymarket.com/api/geoblock",headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=10) as r:return json.loads(r.read().decode())

async def main(a):
 load_env()
 from polymarket import AsyncSecureClient
 key=os.getenv("SIGNER_PRIVATE_KEY")
 if not key:raise RuntimeError("SIGNER_PRIVATE_KEY missing")
 client=await AsyncSecureClient.create(private_key=key)
 try:
  geo=await asyncio.to_thread(geoblock)
  deadline=time.time()+360
  market=None
  while time.time()<deadline:
   markets=await asyncio.to_thread(PolymarketMarketDiscovery.get_active_btc_markets,True,True)
   now=int(time.time()*1000)
   active=[m for m in markets if m.get("market_key")=="5m" and m.get("active") is True and (m.get("metadata") or {}).get("acceptingOrders") is True]
   candidates=[m for m in active if (m.get("expiry_ts_ms") or 0)-now>=120000]
   market=min(candidates,key=lambda m:m["expiry_ts_ms"],default=None)
   if market:break
   diag=[{"slug":m.get("slug"),"seconds_remaining":round(((m.get("expiry_ts_ms") or 0)-now)/1000,3)} for m in active]
   print("WAITING_FOR_FRESH_5M",json.dumps(diag),flush=True)
   await asyncio.sleep(5)
  if not market:raise RuntimeError("NO_FRESH_BTC_5M_MARKET_AFTER_360S")
  token=(market.get("token_ids") or {}).get(a.side)
  if not token:raise RuntimeError("TOKEN_NOT_FOUND")
  book=await client.get_order_book(token_id=str(token))
  asks=getattr(book,"asks",None) or []
  if not asks:raise RuntimeError("NO_ASK_DEPTH")
  rows=sorted(asks,key=lambda x:float(getattr(x,"price",999)))
  ask=float(getattr(rows[0],"price"))
  meta=market.get("metadata") or {}
  staged=StagedClobExecutor(client)
  order=staged.prepare_buy(signal_id=f"manual-smoke-{now}",market_slug=market.get("slug",""),token_id=str(token),notional=a.notional,best_ask=ask,tick_size=float(meta.get("orderPriceMinTickSize",.01)),min_order_size=float(meta.get("orderMinSize",5)))
  gate=LiveArmGate(LiveArmConfig(max_notional=25.0,smoke_notional=5.0))
  state=gate.status(session_token=a.session_token,open_positions=0,session_pnl=0,geoblock_blocked=bool(geo.get("blocked")),market_rotated=False,book_available=True)
  preview={"mode":"ONE_SHOT_LIVE_SMOKE","execute_requested":a.execute,"geoblock":geo,"market":market.get("slug"),"side":a.side,"best_ask":ask,"order":order.__dict__,"gate":state}
  print(json.dumps(preview,indent=2,default=str))
  if not a.execute:
   print("PREVIEW_ONLY: no order submitted");return
  if not state["armed"]:raise RuntimeError("LIVE_GATE_REJECT:"+",".join(state["reasons"]))
  if a.notional>5.0:raise RuntimeError("FIRST_SMOKE_MAX_5_USDC")
  transport=LiveClobTransport(client)
  result=await transport.submit_limit(order=order)
  print("LIVE_ENTRY_RESPONSE")
  print(json.dumps(result,indent=2,default=str))
  print("STOP_AFTER_ENTRY: inspect response/order state before any automated exit")
 finally:
  await client.close()

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--side",choices=["UP","DOWN"],required=True)
 p.add_argument("--notional",type=float,default=5.0)
 p.add_argument("--session-token")
 p.add_argument("--execute",action="store_true")
 asyncio.run(main(p.parse_args()))
