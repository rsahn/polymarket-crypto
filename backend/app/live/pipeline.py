"""Safe V1 -> Risk -> CLOB dry-run -> journal -> shadow comparison pipeline."""
import json,time
from pathlib import Path
from app.live.executor import LiveExecutor,OrderIntent
from app.live.clob_dry_run import ClobDryRunAdapter
from app.live.shadow import compare_shadow_live

class DryRunPipeline:
    def __init__(self, journal:Path):
        self.executor=LiveExecutor();self.clob=ClobDryRunAdapter();self.journal=Path(journal)
        self.journal.parent.mkdir(parents=True,exist_ok=True)

    def _write(self,event):
        with self.journal.open("a",encoding="utf-8") as f:f.write(json.dumps(event,sort_keys=True)+"\n")

    async def process(self,*,signal_id,market_slug,token_id,side,best_ask,
                      bankroll=100.0,open_positions=0,session_pnl=0.0,paper=None):
        intent=OrderIntent(signal_id,market_slug,token_id,side,25.0)
        gate=await self.executor.submit(intent,bankroll=bankroll,
            open_positions=open_positions,session_pnl=session_pnl)
        event={"ts_ms":int(time.time()*1000),"signal_id":signal_id,"risk_gate":gate}
        if gate["status"]!="DRY_RUN":
            event["status"]=gate["status"];self._write(event);return event
        prepared=self.clob.prepare_buy(signal_id=signal_id,market_slug=market_slug,
            token_id=token_id,notional=25.0,best_ask=best_ask)
        event["prepared_order"]=self.clob.serialize(prepared)
        event["status"]="DRY_RUN_READY"
        if paper is not None:
            event["shadow_comparison"]=compare_shadow_live(signal_id=signal_id,paper=paper,live={})
        self._write(event);return event
