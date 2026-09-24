"""Deterministic replay of the previously observed real D6 signal through the
current NO-SUBMIT lifecycle. No network calls and no order submission.
"""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.live.clob_staged import StagedClobExecutor,LifecycleJournal,simulate_lifecycle

class NoNetworkClient:
    pass

async def main():
    out=ROOT/"analysis"/"d6_replay_validation"
    out.mkdir(parents=True,exist_ok=True)
    executor=StagedClobExecutor(NoNetworkClient())
    order=executor.prepare_buy(
        signal_id="1790279791870",
        market_slug="btc-updown-5m-1790279700",
        token_id="39360364743737186856890943742790400901889374934310999036224743283441056448445",
        notional=25.0,best_ask=0.73,tick_size=0.01,min_order_size=5.0,
    )
    staged=await executor.stage(order)
    life=LifecycleJournal(out/"live_staging_lifecycle.jsonl")
    final=await simulate_lifecycle(order=order,entry_fill_ratio=1.0,exit_price=0.80,journal=life)
    result={"source":"observed-real-signal-replay","btc_move":-0.0005021182336372165,
            "staged":staged,"final":final,
            "valid":staged["submit_allowed"] is False and final["state"]=="CLOSED"}
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    asyncio.run(main())
