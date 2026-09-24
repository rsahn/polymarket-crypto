from app.live.clob_staged import KillSwitch,SimulatedLifecycle

def test_full_fill_exit():
 s=SimulatedLifecycle();s.ack();s.fill(size=10,price=.4,requested_size=10)
 assert s.state=="FILLED" and s.open_size==10
 s.exit_fill(size=10,price=.41)
 assert s.state=="CLOSED" and round(s.realized_pnl,8)==.1

def test_partial_cancel_then_exit():
 s=SimulatedLifecycle();s.ack();s.fill(size=4,price=.5,requested_size=10);s.cancel()
 assert s.state=="CANCELLED_PARTIAL" and s.open_size==4
 s.exit_fill(size=4,price=.49)
 assert s.state=="CLOSED" and round(s.realized_pnl,8)==-.04

def test_kill_switch():
 k=KillSwitch()
 assert k.check(open_positions=0,session_pnl=0)["allow"]
 assert not k.check(open_positions=1,session_pnl=0)["allow"]
 assert not k.check(open_positions=0,session_pnl=-25)["allow"]
 assert not k.check(open_positions=0,session_pnl=0,geoblock_blocked=True)["allow"]
 assert not k.check(open_positions=0,session_pnl=0,market_rotated=True)["allow"]
 assert not k.check(open_positions=0,session_pnl=0,book_available=False)["allow"]


def test_append_only_lifecycle_journal(tmp_path):
 import asyncio,json
 from app.live.clob_staged import LifecycleJournal,StagedLimitOrder,simulate_lifecycle
 order=StagedLimitOrder("sig1","slug","token","BUY",25,.5,50,.01,5)
 journal=LifecycleJournal(tmp_path/"life.jsonl")
 final=asyncio.run(simulate_lifecycle(order=order,entry_fill_ratio=.4,exit_price=.51,journal=journal))
 rows=[json.loads(x) for x in (tmp_path/"life.jsonl").read_text().splitlines()]
 assert [x["event"] for x in rows]==["PREPARED","ACK","PARTIAL_FILL","CANCEL_REMAINDER","EXIT_FILL"]
 assert all(x["submit_allowed"] is False for x in rows)
 assert final["state"]=="CLOSED" and round(final["realized_pnl"],8)==.2


def test_timeout_and_entry_invariants():
 from app.live.clob_staged import ExecutionInvariantGuard
 g=ExecutionInvariantGuard()
 assert g.validate_entry(open_positions=0,session_pnl=0,geoblock_blocked=False,market_rotated=False,book_available=True,seconds_remaining=180)["allow"]
 for kwargs in (
  dict(open_positions=1,session_pnl=0,geoblock_blocked=False,market_rotated=False,book_available=True,seconds_remaining=180),
  dict(open_positions=0,session_pnl=-25,geoblock_blocked=False,market_rotated=False,book_available=True,seconds_remaining=180),
  dict(open_positions=0,session_pnl=0,geoblock_blocked=True,market_rotated=False,book_available=True,seconds_remaining=180),
  dict(open_positions=0,session_pnl=0,geoblock_blocked=False,market_rotated=True,book_available=True,seconds_remaining=180),
  dict(open_positions=0,session_pnl=0,geoblock_blocked=False,market_rotated=False,book_available=False,seconds_remaining=180),
  dict(open_positions=0,session_pnl=0,geoblock_blocked=False,market_rotated=False,book_available=True,seconds_remaining=119),
 ):
  assert not g.validate_entry(**kwargs)["allow"]
 assert g.timeout_action(state="PREPARED",elapsed_ms=1499)=="WAIT"
 assert g.timeout_action(state="PREPARED",elapsed_ms=1500)=="ABORT_NO_ACK"
 assert g.timeout_action(state="ACKED",elapsed_ms=2000)=="CANCEL_REMAINDER"
 assert g.timeout_action(state="PARTIAL",elapsed_ms=2000)=="CANCEL_REMAINDER"
 assert g.timeout_action(state="FILLED",elapsed_ms=2000)=="EXIT_RETRY_OR_KILL"
 assert g.timeout_action(state="EXIT_PARTIAL",elapsed_ms=2000)=="EXIT_RETRY_OR_KILL"
