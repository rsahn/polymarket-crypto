"""Capacity curve for D6 fills: 1..10 x 25-unit tranches, depth-aware entry/exit."""
import argparse,json
from pathlib import Path

def fill_asks(levels,budget):
 rem=float(budget);cost=shares=0.
 for p,q in levels:
  p=float(p);q=float(q)
  if p<=0 or q<=0:continue
  take=min(q,rem/p);cost+=take*p;shares+=take;rem-=take*p
  if rem<=1e-9:break
 return cost,shares,(cost/shares if shares else None),rem
def sell_bids(levels,shares):
 rem=float(shares);proceeds=sold=0.
 for p,q in levels:
  p=float(p);q=float(q)
  if p<=0 or q<=0 or rem<=1e-9:continue
  take=min(q,rem);proceeds+=take*p;sold+=take;rem-=take
 return proceeds,sold,(proceeds/sold if sold else None),rem

def main():
 p=argparse.ArgumentParser();p.add_argument("books_json",type=Path)
 p.add_argument("--out",type=Path,required=True);p.add_argument("--max-tranches",type=int,default=10)
 a=p.parse_args();d=json.loads(a.books_json.read_text(encoding="utf-8"))
 # Input is a list of audited signal records with entry_asks/exit_bids.
 signals=d if isinstance(d,list) else d.get("signals",[])
 out=[]
 for s in signals:
  rows=[];prev=0.
  for n in range(1,a.max_tranches+1):
   budget=25.*n;cost,shares,evwap,unspent=fill_asks(s["entry_asks"],budget)
   proceeds,sold,xvwap,remaining=sell_bids(s["exit_bids"],shares)
   realized_cost=cost*(sold/shares) if shares else 0.;pnl=proceeds-realized_cost
   rows.append({"tranches":n,"target_notional":budget,"cost":cost,"entry_vwap":evwap,
    "shares":shares,"exit_vwap":xvwap,"sold_shares":sold,"remaining_shares":remaining,
    "realized_pnl":pnl,"marginal_pnl":pnl-prev,"exit_complete":remaining<=1e-9})
   prev=pnl
  out.append({"signal_ts_ms":s["signal_ts_ms"],"side":s["side"],"slug":s["slug"],"curve":rows})
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2),encoding="utf-8")
 print(json.dumps([{"signal_ts_ms":x["signal_ts_ms"],"side":x["side"],
  "best_tranches_by_realized_pnl":max(x["curve"],key=lambda r:r["realized_pnl"])["tranches"],
  "best_realized_pnl":max(r["realized_pnl"] for r in x["curve"])} for x in out],indent=2))
if __name__=="__main__":main()
