"""D6 V1 live paper trading. Public feeds only; NEVER sends real orders."""
import argparse,asyncio,json,types,sys,os
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from d6.paper_live import PaperLedger,V1
from app.d5.live import run as collect_live
from app.live.pipeline import DryRunPipeline
from app.live.clob_staged import StagedClobExecutor,ExecutionInvariantGuard,LifecycleJournal,simulate_lifecycle

def fill(asks,budget):
 rem=float(budget);cost=shares=0.0
 for p,q in asks:
  p=float(p);q=float(q)
  if p<=0 or q<=0:continue
  take=min(q,rem/p);cost+=take*p;shares+=take;rem-=take*p
  if rem<=1e-9:break
 return cost,shares,(cost/shares if shares else None)

def liquidate(bids,shares):
 rem=float(shares);proceeds=sold=0.0
 for p,q in bids:
  p=float(p);q=float(q)
  if p<=0 or q<=0 or rem<=1e-9:continue
  take=min(q,rem);proceeds+=take*p;sold+=take;rem-=take
 return proceeds,sold,(proceeds/sold if sold else None),rem

async def main_async(a):
 ledger=PaperLedger(a.out_dir,a.capital,a.snapshot_hours)
 frozen={**V1,"initial_capital":a.capital,"snapshot_hours":a.snapshot_hours,"latency_ms":a.latency_ms,"hold_ms":a.hold_ms}
 a.out_dir.mkdir(parents=True,exist_ok=True)
 (a.out_dir/"STRATEGY_V1_FROZEN.json").write_text(json.dumps(frozen,indent=2,sort_keys=True),encoding="utf-8")
 btc=deque(maxlen=4096);latest={};pending=set();last_signal=-10**18
 dryrun=DryRunPipeline(a.out_dir/"live_dry_run.jsonl") if a.live_dry_run else None
 staged_client=None;staged=None;staged_journal=a.out_dir/"live_staging.jsonl";guard=ExecutionInvariantGuard();life_journal=LifecycleJournal(a.out_dir/"live_staging_lifecycle.jsonl")
 if a.live_staging:
  if os.getenv("REAL_ORDERS_ENABLED","false").lower()=="true":raise RuntimeError("LIVE_STAGING_REQUIRES_REAL_ORDERS_DISABLED")
  from polymarket import AsyncSecureClient
  key=os.getenv("SIGNER_PRIVATE_KEY")
  if not key:raise RuntimeError("SIGNER_PRIVATE_KEY missing for live staging")
  staged_client=await AsyncSecureClient.create(private_key=key);staged=StagedClobExecutor(staged_client)

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
  exit_bids=exit_snap[side.lower()].get("bids") or []
  if not exit_bids:
   ledger.record_skip({"signal_ts_ms":signal_ts,"side":side,"reason":"NO_EXIT_DEPTH","slug":exit_snap.get("market_slug")});return
  for name,(cost,shares,vwap,slug) in entries.items():
   if exit_snap.get("market_slug")!=slug:
    ledger.record_skip({"signal_ts_ms":signal_ts,"side":side,"reason":"MARKET_ROTATION","slug":slug});continue
   proceeds,sold,exit_vwap,remaining=liquidate(exit_bids,shares)
   realized_cost=cost*(sold/shares) if shares else 0.0
   pnl=proceeds-realized_cost
   ledger.record_fill(name,{"signal_ts_ms":signal_ts,"side":side,"btc_move":move,"slug":slug,
     "entry_vwap":vwap,"cost":cost,"shares":shares,"exit_vwap":exit_vwap,
     "exit_sold_shares":sold,"exit_remaining_shares":remaining,"proceeds":proceeds,
     "realized_cost":realized_cost,"exit_complete":remaining<=1e-9},pnl)
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
  if dryrun:
   snap=latest.get("5m")
   if snap:
    q=snap.get(side.lower()) or {};ask=q.get("ask");token=q.get("token_id")
    if ask is not None and token:
     dr=asyncio.create_task(dryrun.process(signal_id=str(tick.recv_ts_ms),market_slug=snap.get("market_slug",""),
       token_id=str(token),side=side,best_ask=float(ask),bankroll=100,open_positions=0,session_pnl=0))
     pending.add(dr);dr.add_done_callback(pending.discard)
  if staged:
   snap=latest.get("5m")
   if snap:
    q=snap.get(side.lower()) or {};ask=q.get("ask");token=q.get("token_id")
    if ask is not None and token:
     expiry=snap.get("expiry_ts_ms") or 0;remaining=(expiry-tick.recv_ts_ms)/1000 if expiry else 999
     gate=guard.validate_entry(open_positions=0,session_pnl=0,geoblock_blocked=False,market_rotated=False,book_available=True,seconds_remaining=remaining)
     if not gate["allow"]:
      with staged_journal.open("a",encoding="utf-8") as fh:fh.write(json.dumps({"signal_id":str(tick.recv_ts_ms),"status":"STAGING_REJECT","reasons":gate["reasons"],"submit_allowed":False},sort_keys=True)+"\n")
      print("D6 LIVE STAGING REJECT",side,gate["reasons"],flush=True)
     else:
      order=staged.prepare_buy(signal_id=str(tick.recv_ts_ms),market_slug=snap.get("market_slug",""),token_id=str(token),notional=25.0,best_ask=float(ask),tick_size=0.01,min_order_size=5.0)
      event=await staged.stage(order)
      with staged_journal.open("a",encoding="utf-8") as fh:fh.write(json.dumps(event,sort_keys=True)+"\\n")
      await simulate_lifecycle(order=order,entry_fill_ratio=1.0,exit_price=float(ask),journal=life_journal)
      print("D6 LIVE STAGING",side,event["mode"],"submit_allowed=",event["submit_allowed"],flush=True)
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
  if staged_client is not None:await staged_client.close()
  print("D6 PAPER LIVE stopped; snapshot=",ledger.snapshot(force=True))

def main():
 p=argparse.ArgumentParser();p.add_argument("--db",type=Path,default=Path("data/d6/d6_paper_live.db"))
 p.add_argument("--out-dir",type=Path,default=Path("analysis/d6/paper_live"));p.add_argument("--capital",type=float,default=500)
 p.add_argument("--snapshot-hours",type=float,default=1);p.add_argument("--latency-ms",type=int,default=250)
 p.add_argument("--hold-ms",type=int,default=500);p.add_argument("--seconds",type=float,default=0)
 p.add_argument("--live-dry-run",action="store_true",help="Mirror V1 signals into safe CLOB dry-run journal")
 p.add_argument("--live-staging",action="store_true",help="Authenticated live-shaped staging; hard-fenced, never submits")
 asyncio.run(main_async(p.parse_args()))
if __name__=="__main__":main()
