import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.live.journal import LiveJournal
from app.live.comparator import compare_execution

def test_journal_roundtrip(tmp_path):
 j=LiveJournal(tmp_path/"live.jsonl");sid=j.signal_id(123,"m","UP")
 j.append("SIGNAL",sid,side="UP");j.append("RISK_DECISION",sid,approved=True)
 assert [x["event_type"] for x in j.events(sid)]==["SIGNAL","RISK_DECISION"]

def test_comparator_metrics():
 r=compare_execution(signal_id="s",paper={"pnl":2,"entry_vwap":.5},
  live={"pnl":1.5,"entry_vwap":.51,"requested_shares":50,"filled_shares":45,"ack_latency_ms":20,"fees":.1})
 assert r["pnl_gap"]==-.5 and r["edge_capture_ratio"]==.75
 assert abs(r["fill_ratio"]-.9)<1e-12 and abs(r["entry_slippage"]-.01)<1e-12
