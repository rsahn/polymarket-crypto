import asyncio
from pathlib import Path
from app.live.pipeline import DryRunPipeline
def test_pipeline_stops_at_dry_run(tmp_path):
 p=DryRunPipeline(tmp_path/"events.jsonl")
 r=asyncio.run(p.process(signal_id="s",market_slug="m",token_id="t",side="UP",best_ask=.5))
 assert r["status"]=="DRY_RUN_READY"
 assert r["prepared_order"]["submit_allowed"] is False
 assert (tmp_path/"events.jsonl").exists()

def test_risk_rejects_over_25(tmp_path):
 p=DryRunPipeline(tmp_path/"over25.jsonl")
 p.executor.risk.limits=type(p.executor.risk.limits)(bankroll_cap=100,max_order_notional=24,max_open_positions=1,session_loss_limit=25)
 r=asyncio.run(p.process(signal_id="s",market_slug="m",token_id="t",side="UP",best_ask=.5))
 assert r["status"]=="RISK_REJECT" and "ORDER_NOTIONAL" in r["risk_gate"]["risk_reasons"]

def test_risk_rejects_bankroll_over_cap(tmp_path):
 p=DryRunPipeline(tmp_path/"bankroll.jsonl")
 r=asyncio.run(p.process(signal_id="s",market_slug="m",token_id="t",side="UP",best_ask=.5,bankroll=101))
 assert r["status"]=="RISK_REJECT" and "BANKROLL_CAP" in r["risk_gate"]["risk_reasons"]

def test_risk_rejects_existing_position(tmp_path):
 p=DryRunPipeline(tmp_path/"position.jsonl")
 r=asyncio.run(p.process(signal_id="s",market_slug="m",token_id="t",side="UP",best_ask=.5,open_positions=1))
 assert r["status"]=="RISK_REJECT" and "OPEN_POSITION_LIMIT" in r["risk_gate"]["risk_reasons"]

def test_risk_rejects_loss_limit(tmp_path):
 p=DryRunPipeline(tmp_path/"loss.jsonl")
 r=asyncio.run(p.process(signal_id="s",market_slug="m",token_id="t",side="UP",best_ask=.5,session_pnl=-25))
 assert r["status"]=="RISK_REJECT" and "SESSION_LOSS_LIMIT" in r["risk_gate"]["risk_reasons"]
