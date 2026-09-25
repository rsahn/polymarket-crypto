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


def test_book_freshness_gate_fail_closed():
 from app.live.clob_staged import BookFreshnessGate
 g=BookFreshnessGate(max_book_age_ms=500)
 assert not g.status(now_ms=1000)["allow"]
 g.on_connect();assert not g.status(now_ms=1000)["allow"]
 g.on_book_synced(initialized=1,required=2,ts_ms=1000);assert not g.status(now_ms=1000)["allow"]
 g.on_book_synced(initialized=2,required=2,ts_ms=1000);assert g.status(now_ms=1499)["allow"]
 stale=g.status(now_ms=1501);assert not stale["allow"] and "BOOK_STALE" in stale["reasons"]
 g.on_book_update(ts_ms=1501);assert g.status(now_ms=1600)["allow"]
 g.on_disconnect();assert not g.status(now_ms=1600)["allow"]
 g.on_connect();assert not g.status(now_ms=1600)["allow"]


def test_night_cycle_full_fill_closes():
 from app.live.clob_staged import SimulatedNightCycle
 r=SimulatedNightCycle().run(requested_size=10,entry_fills=[(10,.4)],exit_fills=[(10,.41)])
 assert r["state"]=="CLOSED" and r["final"]["open_size"]==0

def test_night_cycle_partial_entry_cancel_then_close():
 from app.live.clob_staged import SimulatedNightCycle
 r=SimulatedNightCycle().run(requested_size=10,entry_fills=[(4,.5)],exit_fills=[(4,.49)])
 assert any(x["event"]=="CANCEL_REMAINDER" for x in r["events"])
 assert r["final"]["state"]=="CLOSED"

def test_night_cycle_zero_fill_fails_closed():
 from app.live.clob_staged import SimulatedNightCycle,SimulatedCycleError
 try:SimulatedNightCycle().run(requested_size=10,entry_fills=[],exit_fills=[])
 except SimulatedCycleError as e:assert str(e)=="ENTRY_NOT_FILLED"
 else:assert False

def test_night_cycle_partial_exit_fails_closed():
 from app.live.clob_staged import SimulatedNightCycle,SimulatedCycleError
 try:SimulatedNightCycle().run(requested_size=10,entry_fills=[(10,.4)],exit_fills=[(6,.41)])
 except SimulatedCycleError as e:assert str(e).startswith("POSITION_NOT_FLAT:")
 else:assert False

def test_night_cycle_multi_fill_weighted_pnl():
 from app.live.clob_staged import SimulatedNightCycle
 r=SimulatedNightCycle().run(requested_size=10,entry_fills=[(4,.4),(6,.5)],exit_fills=[(3,.55),(7,.56)])
 assert r["final"]["state"]=="CLOSED"
 assert round(r["final"]["average_fill_price"],8)==.46
 assert round(r["final"]["realized_pnl"],8)==.97


def test_position_state_store_blocks_unclosed_restart(tmp_path):
 from app.live.clob_staged import PositionStateStore,PersistedPositionState
 store=PositionStateStore(tmp_path/"position.json")
 assert not store.assert_flat_or_recover()["allow_new_entry"]
 s=PersistedPositionState("sig","slug","token",state="FILLED",filled_shares=10)
 store.save(s)
 loaded=store.load()
 assert loaded.open_shares==10
 gate=store.assert_flat_or_recover()
 assert not gate["allow_new_entry"] and gate["reason"]=="REMOTE_RECONCILIATION_REQUIRED"

def test_position_state_store_allows_closed_restart(tmp_path):
 from app.live.clob_staged import PositionStateStore,PersistedPositionState
 store=PositionStateStore(tmp_path/"position.json")
 s=PersistedPositionState("sig","slug","token",state="CLOSED",filled_shares=10,sold_shares=10)
 store.save(s)
 gate=store.assert_flat_or_recover()
 assert not gate["allow_new_entry"] and gate["reason"]=="REMOTE_RECONCILIATION_REQUIRED"


def test_reconciler_closed_local_requires_remote():
 import asyncio
 from app.live.clob_staged import RecoveryReconciler,PersistedPositionState
 class C:
  async def get_order(self,**kw):raise AssertionError("must not query")
 s=PersistedPositionState("s","slug","t",state="CLOSED",filled_shares=5,sold_shares=5)
 r=asyncio.run(RecoveryReconciler(C()).reconcile(s))
 assert not r["allow_new_entry"] and r["reason"]=="ORDER_ID_MISSING"

def test_reconciler_unknown_remote_fails_closed():
 import asyncio
 from app.live.clob_staged import RecoveryReconciler,PersistedPositionState
 class C:
  async def get_order(self,**kw):raise RuntimeError("network")
 s=PersistedPositionState("s","slug","t",state="FILLED",entry_order_id="oid",filled_shares=5)
 r=asyncio.run(RecoveryReconciler(C()).reconcile(s))
 assert not r["allow_new_entry"] and r["reason"]=="RECOVERY_REQUIRED"

def test_reconciler_remote_state_requires_review():
 import asyncio
 from app.live.clob_staged import RecoveryReconciler,PersistedPositionState
 class C:
  async def get_order(self,**kw):return {"status":"LIVE","size_matched":"2"}
 s=PersistedPositionState("s","slug","t",state="PARTIAL",entry_order_id="oid",filled_shares=2)
 r=asyncio.run(RecoveryReconciler(C()).reconcile(s))
 assert not r["allow_new_entry"] and r["reason"]=="REMOTE_REVIEW_REQUIRED"


def test_remote_projector_open_partial_full():
 from app.live.clob_staged import RemoteStateProjector,PersistedPositionState
 p=RemoteStateProjector();s=PersistedPositionState("s","slug","t")
 r=p.apply(s,{"known":True,"status":"LIVE","original_size":10,"filled_size":0,"remaining_size":10})
 assert r["ok"] and s.state=="ACKED"
 r=p.apply(s,{"known":True,"status":"LIVE","original_size":10,"filled_size":4,"remaining_size":6})
 assert r["ok"] and s.state=="PARTIAL" and s.filled_shares==4
 r=p.apply(s,{"known":True,"status":"MATCHED","original_size":10,"filled_size":10,"remaining_size":0})
 assert r["ok"] and s.state=="FILLED" and s.filled_shares==10

def test_remote_projector_unknown_status_fails_closed():
 from app.live.clob_staged import RemoteStateProjector,PersistedPositionState
 s=PersistedPositionState("s","slug","t")
 r=RemoteStateProjector().apply(s,{"known":True,"status":"MYSTERY","original_size":10,"filled_size":0,"remaining_size":10})
 assert not r["ok"] and r["reason"]=="UNMAPPED_REMOTE_STATUS"

def test_remote_projector_invalid_sizes_fails_closed():
 from app.live.clob_staged import RemoteStateProjector,PersistedPositionState
 s=PersistedPositionState("s","slug","t")
 r=RemoteStateProjector().apply(s,{"known":True,"status":"LIVE","original_size":5,"filled_size":6,"remaining_size":0})
 assert not r["ok"] and r["reason"]=="INVALID_REMOTE_SIZES"


def test_readonly_sync_persists_remote_state(tmp_path):
 import asyncio
 from app.live.clob_staged import ReadOnlyPositionSynchronizer,PositionStateStore,PersistedPositionState
 class C:
  async def get_order(self,**kw):
   return {"status":"LIVE","original_size":"10","size_matched":"4"}
 store=PositionStateStore(tmp_path/"position.json")
 state=PersistedPositionState("s","slug","t",entry_order_id="oid")
 r=asyncio.run(ReadOnlyPositionSynchronizer(C(),store).sync(state))
 assert r["ok"] and r["reason"]=="SYNCED_AND_PERSISTED"
 loaded=store.load()
 assert loaded.state=="PARTIAL" and loaded.filled_shares==4

def test_readonly_sync_unknown_remote_does_not_persist(tmp_path):
 import asyncio
 from app.live.clob_staged import ReadOnlyPositionSynchronizer,PositionStateStore,PersistedPositionState
 class C:
  async def get_order(self,**kw):return {"foo":"bar"}
 store=PositionStateStore(tmp_path/"position.json")
 state=PersistedPositionState("s","slug","t",entry_order_id="oid")
 r=asyncio.run(ReadOnlyPositionSynchronizer(C(),store).sync(state))
 assert not r["ok"]
 assert not (tmp_path/"position.json").exists()
