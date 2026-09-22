"""D6 V1 paper-live launcher scaffold.

This launcher intentionally refuses real-order mode. Wiring to the validated D5
live feed is the next integration step; the frozen V1 contract is emitted now.
"""
import argparse,json,time
from pathlib import Path
from d6.paper_live import PaperLedger,V1

def main():
 p=argparse.ArgumentParser();p.add_argument("--out-dir",type=Path,default=Path("analysis/d6/paper_live"))
 p.add_argument("--capital",type=float,default=500);p.add_argument("--snapshot-hours",type=float,default=10)
 p.add_argument("--print-contract",action="store_true");a=p.parse_args()
 ledger=PaperLedger(a.out_dir,a.capital,a.snapshot_hours)
 contract={**V1,"initial_capital":a.capital,"snapshot_hours":a.snapshot_hours}
 (a.out_dir/"STRATEGY_V1_FROZEN.json").parent.mkdir(parents=True,exist_ok=True)
 (a.out_dir/"STRATEGY_V1_FROZEN.json").write_text(json.dumps(contract,indent=2,sort_keys=True),encoding="utf-8")
 ledger.snapshot(force=True)
 print(json.dumps(contract,indent=2,sort_keys=True))
 print("D6 PAPER V1 scaffold initialized; real_orders=False")

if __name__=="__main__":main()
