"""Replay frozen D6 V1 signals with depth-aware entry AND exit. Research only."""
import argparse,json,sqlite3,zlib
from bisect import bisect_left
from pathlib import Path

def unpack(v):
 if isinstance(v,bytes):v=zlib.decompress(v).decode("utf-8")
 return json.loads(v)

def walk_asks(levels,budget):
 rem=float(budget);cost=shares=0.0
 for p,q in levels:
  p=float(p);q=float(q)
  if p<=0 or q<=0:continue
  take=min(q,rem/p);cost+=take*p;shares+=take;rem-=take*p
  if rem<=1e-9:break
 return cost,shares,(cost/shares if shares else None),rem

def walk_bids(levels,shares):
 rem=float(shares);proceeds=sold=0.0
 for p,q in levels:
  p=float(p);q=float(q)
  if p<=0 or q<=0 or rem<=1e-9:continue
  take=min(q,rem);proceeds+=take*p;sold+=take;rem-=take
 return proceeds,sold,(proceeds/sold if sold else None),rem

def main():
 p=argparse.ArgumentParser();p.add_argument("db",type=Path);p.add_argument("--paper-json",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True);p.add_argument("--latency-ms",type=int,default=250);p.add_argument("--hold-ms",type=int,default=500)
 a=p.parse_args();paper=json.loads(a.paper_json.read_text(encoding="utf-8"))
 db=sqlite3.connect(f"file:{a.db.resolve()}?mode=ro",uri=True)
 try:
  # Compact DB intentionally has no sessions table; its provenance is the
  # frozen paper JSON plus the extracted signal windows.
  sid="compact-signal-windows"
  signals=paper.get("signals",[])
  # Compact extractor schema: books already contains only the 13 signal windows.
  books={"UP":[],"DOWN":[]}
  q="""SELECT received_ts_ms,market_slug,side,best_bid,best_ask,bids_json,asks_json
       FROM books"""
  for ts,slug,side,bid,ask,bids,asks in db.execute(q):
   books[side].append((int(ts),slug,bid,ask,unpack(bids),unpack(asks)))
  for side in books:books[side].sort(key=lambda x:x[0])
  times={s:[x[0] for x in arr] for s,arr in books.items()}
  def at(side,ts,slug):
   arr=books[side];i=bisect_left(times[side],ts)
   while i<len(arr) and arr[i][1]!=slug:i+=1
   return arr[i] if i<len(arr) else None

  portfolios={"fixed_25":500.0,"fixed_50":500.0,"fixed_100":500.0,"dynamic_depth":500.0}
  budgets={"fixed_25":25.0,"fixed_50":50.0,"fixed_100":100.0}
  trades=[];skips=[]
  for sig in signals:
   st=int(sig["ts_ms"]);side=sig["side"]
   # Resolve market from first same-side accepted book at entry time.
   arr=books[side];i=bisect_left(times[side],st+a.latency_ms)
   if i>=len(arr):skips.append({"signal_ts_ms":st,"reason":"NO_ENTRY_BOOK"});continue
   entry=arr[i];slug=entry[1]
   exitb=at(side,st+a.latency_ms+a.hold_ms,slug)
   if exitb is None:skips.append({"signal_ts_ms":st,"reason":"NO_EXIT_BOOK","slug":slug});continue
   available=sum(float(p)*float(q) for p,q in entry[5] if float(p)>0 and float(q)>0)
   dyn=min(100.0,available*.25); per={**budgets,"dynamic_depth":dyn}
   for name,target in per.items():
    budget=min(target,portfolios[name])
    cost,shares,evwap,unspent=walk_asks(entry[5],budget)
    if shares<=0:continue
    proceeds,sold,xvwap,remaining=walk_bids(exitb[4],shares)
    realized_cost=cost*(sold/shares)
    realized_pnl=proceeds-realized_cost
    portfolios[name]+=realized_pnl
    trades.append({"portfolio":name,"signal_ts_ms":st,"side":side,"slug":slug,
      "entry_ts_ms":entry[0],"cost":cost,"shares":shares,"entry_vwap":evwap,"unspent_budget":unspent,
      "exit_ts_ms":exitb[0],"sold_shares":sold,"exit_vwap":xvwap,"proceeds":proceeds,
      "remaining_shares":remaining,"realized_cost":realized_cost,"realized_pnl":realized_pnl,
      "capital_after":portfolios[name],"exit_complete":remaining<=1e-9})
  report={"contract":"D6_DEPTH_AWARE_REPLAY","session_id":sid,"latency_ms":a.latency_ms,"hold_ms":a.hold_ms,
    "signal_count":len(signals),"portfolios":{k:{"capital":v,"realized_pnl":v-500.0} for k,v in portfolios.items()},
    "trades":trades,"skips":skips,
    "note":"P&L is realized liquidation P&L only; unsold shares are explicit inventory and are not synthetically marked."}
  a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8")
  print(json.dumps({"signal_count":len(signals),"portfolios":report["portfolios"],"trade_rows":len(trades),"skips":len(skips)},indent=2))
 finally:db.close()
if __name__=="__main__":main()
