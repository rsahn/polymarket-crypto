"""Exercise the live pipeline without credentials or order submission."""
import argparse,asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from app.live.pipeline import DryRunPipeline
async def run(a):
 p=DryRunPipeline(a.journal)
 r=await p.process(signal_id=a.signal_id,market_slug=a.slug,token_id=a.token_id,
  side=a.side,best_ask=a.best_ask,bankroll=a.bankroll,open_positions=0,session_pnl=0)
 print(json.dumps(r,indent=2))
def main():
 p=argparse.ArgumentParser();p.add_argument("--signal-id",default="manual-smoke")
 p.add_argument("--slug",default="dry-run-market");p.add_argument("--token-id",default="dry-run-token")
 p.add_argument("--side",choices=["UP","DOWN"],default="UP");p.add_argument("--best-ask",type=float,default=.50)
 p.add_argument("--bankroll",type=float,default=100);p.add_argument("--journal",type=Path,default=Path("analysis/d6/live_dry_run/events.jsonl"))
 asyncio.run(run(p.parse_args()))
if __name__=="__main__":main()
