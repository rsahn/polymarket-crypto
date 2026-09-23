"""Summarize a D6 depth-aware replay JSON. Research/paper only."""
import argparse,json,math
from collections import defaultdict
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument("replay",type=Path);a=p.parse_args()
 d=json.loads(a.replay.read_text(encoding="utf-8")); groups=defaultdict(list)
 for t in d["trades"]:groups[t["portfolio"]].append(t)
 out={}
 for name,ts in groups.items():
  pnls=[float(t["realized_pnl"]) for t in ts];wins=[x for x in pnls if x>0];loss=[x for x in pnls if x<0]
  gp=sum(wins);gl=-sum(loss);partials=[t for t in ts if not t["exit_complete"]]
  byside={}
  for side in ("UP","DOWN"):
   z=[t for t in ts if t["side"]==side];byside[side]={"trades":len(z),"pnl":sum(float(x["realized_pnl"]) for x in z)}
  out[name]={"trades":len(ts),"wins":len(wins),"losses":len(loss),"flat":len(ts)-len(wins)-len(loss),
   "win_rate":len(wins)/len(ts) if ts else None,"realized_pnl":sum(pnls),
   "avg_pnl":sum(pnls)/len(ts) if ts else None,"avg_win":sum(wins)/len(wins) if wins else None,
   "avg_loss":sum(loss)/len(loss) if loss else None,"profit_factor":gp/gl if gl else None,
   "best_trade":max(pnls) if pnls else None,"worst_trade":min(pnls) if pnls else None,
   "complete_exits":len(ts)-len(partials),"partial_exits":len(partials),
   "remaining_shares":sum(float(t["remaining_shares"]) for t in partials),"by_side":byside}
 print(json.dumps(out,indent=2))
if __name__=="__main__":main()
