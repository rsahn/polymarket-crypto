"""D6 V1 live paper trading. Public feeds only; NEVER sends real orders."""
import argparse,asyncio,json,types,sys
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from d6.paper_live import PaperLedger,V1
from app.d5.live import run as collect_live

def fill(asks,budget):
 rem=float(budget);cost=shares=0.0
 for p,q in asks:
  p=float(p);q=float(q)
  if p<=0 or q<=0:continue
  take=min(q,rem/p);cost+=take*p;shares+=take;rem-=take*p
  if rem<=1e-9:break
 return cost,shares,(cost/shares if shares else None)

async def main_async(a):
 ledger=PaperLedger(a.out_dir,a.capital,a.snapshot_hours)
 frozen={**V1,"initial_capital":a.capital,"snapshot_hours":a.snapshot_hours,"latency_ms":a.latency_ms,"hold_ms":a.hold_ms}
 a.out_dir.mkdir(parents=True,exist_ok=True)
 (a.out_dir/"STRATEGY_V1_FROZEN.json").write_text(json.dumps(frozen,indent=2,sort_keys=True),encoding="utf-8")
 btc=deque(maxlen=4096);latest={};pending=set();last_signal=-10**18

 async def execute_signal(signal_ts,move,side):
  await asyncio.sleep(a.latency_ms/1000)
  snap=latest.get("5m")
  if not snap:
   ledger.record_skip({"signal_ts_ms":signal_ts,"side":side,"reason":"NO_BOOK"});return
  q=snap[side.lower()];asks=q.get("asks") or []
  if not asks:
   ledger.record_skip({"signal_ts_ms":signal_ts,"side":side,"reason":"NO_DEPTH","slug":snap.get("market_slug")});return
  available=sum(float(p)*float(n) for p,n in asks);entries={}
  for name,budget in ledger.sizes(available).items():
   budget=min(budget,ledger.portfolios[name].capital)
   cost,shares,vwap=fill(asks,budget)
   if shares:entries[name]=(cost,shares,vwap,snap["market_slug"])
  await asyncio.sleep(a.hold_ms/1000)
  exit_snap=latest.get("5m")
  if not exit_snap:
   ledger.record_skip({"signal_ts_ms":signal_ts,"side":side,"reason":"NO_EXIT_BOOK"});return
  opp="down" if side=="UP" else "up";opp_ask=exit_snap[opp].get("ask")
  if opp_ask is None:
   ledger.record_skip({"signal_ts_ms":signal_ts,"side":side,"reason":"NO_EXIT_BBO","slug":exit_snap.get("market_slug")});return
  exit_price=max(0.0,1.0-float(opp_ask))
  for name,(cost,shares,vwap,slug) in entries.items():
   if exit_snap.get("market_slug")!=slug:
    ledger.record_skip({"signal_ts_ms":signal_ts,"side":side,"reason":"MARKET_ROTATION","slug":slug});continue
   ledger.record_fill(name,{"signal_ts_ms":signal_ts,"side":side,"btc_move":move,"slug":slug,
     "entry_vwap":vwap,"cost":cost,"shares":shares,"exit_price":exit_price},shares*exit_price-cost)
  ledger.snapshot()

 async def on_btc(tick):
  nonlocal last_signal
  btc.append((tick.recv_ts_ms,float(tick.price)));cutoff=tick.recv_ts_ms-250
  prior=next((x for x in btc if x[0]>=cutoff),None)
  if prior is None or prior[0]>=tick.recv_ts_ms:return
  move=float(tick.price)/prior[1]-1
  if abs(move)<.0005 or tick.recv_ts_ms-last_signal<1000:return
  last_signal=tick.recv_ts_ms;side="UP" if move>0 else "DOWN"
  ledger.record_signal({"ts_ms":tick.recv_ts_ms,"btc_move":move,"side":side})
  task=asyncio.create_task(execute_signal(tick.recv_ts_ms,move,side));pending.add(task);task.add_done_callback(pending.discard)

 async def on_quote(duration,snapshot):latest[duration]=snapshot
 async def snapshots():
  while True:
   await asyncio.sleep(60);ledger.snapshot()

 stop=asyncio.Event()
 live_args=types.SimpleNamespace(db=a.db,seconds=a.seconds,reconnect_after=0,min_free_bytes=5*1024**3,
  on_progress=None,timestamp_contract="D5.1",stop_event=stop,on_live_quote=on_quote,on_live_btc=on_btc)
 snap_task=asyncio.create_task(snapshots())
 try:await collect_live(live_args)
 finally:
  snap_task.cancel();await asyncio.gather(snap_task,return_exceptions=True)
  if pending:await asyncio.gather(*pending,return_exceptions=True)
  print("D6 PAPER LIVE stopped; snapshot=",ledger.snapshot(force=True))

def main():
 p=argparse.ArgumentParser();p.add_argument("--db",type=Path,default=Path("data/d6/d6_paper_live.db"))
 p.add_argument("--out-dir",type=Path,default=Path("analysis/d6/paper_live"));p.add_argument("--capital",type=float,default=500)
 p.add_argument("--snapshot-hours",type=float,default=1);p.add_argument("--latency-ms",type=int,default=250)
 p.add_argument("--hold-ms",type=int,default=500);p.add_argument("--seconds",type=float,default=0)
 asyncio.run(main_async(p.parse_args()))
if __name__=="__main__":main()
