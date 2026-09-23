import asyncio
from pathlib import Path
from app.live.pipeline import DryRunPipeline
def test_pipeline_stops_at_dry_run(tmp_path):
 p=DryRunPipeline(tmp_path/"events.jsonl")
 r=asyncio.run(p.process(signal_id="s",market_slug="m",token_id="t",side="UP",best_ask=.5))
 assert r["status"]=="DRY_RUN_READY"
 assert r["prepared_order"]["submit_allowed"] is False
 assert (tmp_path/"events.jsonl").exists()
