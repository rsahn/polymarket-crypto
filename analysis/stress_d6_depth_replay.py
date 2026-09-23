"""Robustness diagnostics for D6 depth-aware replay."""
import argparse,json
from collections import defaultdict
from pathlib import Path
def stats(ts):
 p=[float(x["realized_pnl"]) for x in ts]
 return {"trades":len(p),"pnl":sum(p),"avg":sum(p)/len(p) if p else None,
 "wins":sum(x>0 for x in p),"losses":sum(x<0 for x in p)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("replay",type=Path);a=ap.parse_args()
 d=json.loads(a.replay.read_text(encoding="utf-8"))
 out={}
 for name in ("fixed_25","fixed_50","fixed_100","dynamic_depth"):
  ts=[x for x in d["trades"] if x["portfolio"]==name]
  ordered=sorted(ts,key=lambda x:x["signal_ts_ms"]); ranked=sorted(ts,key=lambda x:x["realized_pnl"],reverse=True)
  buckets=defaultdict(list)
  for x in ts:
   v=float(x["entry_vwap"])
   k="<0.10" if v<.10 else "0.10-0.30" if v<.30 else "0.30-0.70" if v<.70 else ">=0.70"
   buckets[k].append(x)
  cum=500.;curve=[]
  for x in ordered:
   cum+=float(x["realized_pnl"]);curve.append({"ts_ms":x["signal_ts_ms"],"pnl":x["realized_pnl"],"capital":cum})
  out[name]={"all":stats(ts),"without_best":stats(ranked[1:]),"without_top2":stats(ranked[2:]),
   "best_two":[{"ts_ms":x["signal_ts_ms"],"pnl":x["realized_pnl"],"side":x["side"],"entry_vwap":x["entry_vwap"]} for x in ranked[:2]],
   "by_side":{s:stats([x for x in ts if x["side"]==s]) for s in ("UP","DOWN")},
   "by_entry_vwap":{k:stats(v) for k,v in sorted(buckets.items())},"cumulative":curve}
 print(json.dumps(out,indent=2))
if __name__=="__main__":main()
