import asyncio
import json
import pytest
from app.live.execution import ExecutionController, ExecutionStore, ExecutionBlocked
from app.live.clob_staged import StagedLimitOrder
from app.live.clob_transport import LiveClobTransport


def order(): return StagedLimitOrder("signal","market","token","BUY",5,.5,10,.01,1)


class Fixture:
    def __init__(self,path,mode="full"):
        self.store=ExecutionStore(path);self.mode=mode;self.calls=[];self.cancelled=False;self.exit_sent=False;self.reads=0
        self.gate=dict(connected=True,book_synced=True,signal_valid=True,recovery_complete=True,
            geoblock_blocked=False,market_slug="market",token_id="token",book_ms=1000,risk_ms=1000,
            signal_ms=1000,geo_ms=1000,expiry_ms=200000,session_pnl=0,open_positions=0,available_usdc=109.16,fillable_shares=20)
        self.controller=ExecutionController(self.store,self,self.account,lambda:dict(self.gate),timeout=.03,clock=lambda:1000)
    async def account(self):
        quantity=0
        if self.calls:
            quantity=6 if self.mode=="late" else 10
            if self.exit_sent:quantity=6 if self.mode=="partial_exit" else 0
        return dict(complete=True,observed_ms=1000,open_order_ids=[],balances={"token":quantity})
    async def submit_limit(self,**kwargs):
        self.calls.append("entry")
        return {"response":{} if self.mode=="ambiguous" else {"order_id":"entry"}}
    async def submit_exit_limit(self,**kwargs):
        self.calls.append(("exit",kwargs["size"]));self.exit_sent=True
        return {"response":{"order_id":"exit"}}
    async def cancel_order(self,**kwargs):self.calls.append("cancel");self.cancelled=True;return {"response":{"success":True}}
    async def get_order(self,order_id):
        self.reads+=1
        if self.mode=="inaccessible":raise OSError("offline")
        filled,size,status=10,10,"MATCHED"
        if order_id=="entry" and self.mode=="late":filled,status=(6,"CANCELLED") if self.cancelled else (4,"LIVE")
        if order_id=="exit" and self.mode=="late":filled=size=6
        if order_id=="exit" and self.mode=="partial_exit":filled,status=4,"CANCELLED"
        return {"response":dict(order_id=order_id,asset_id="token",side="BUY" if order_id=="entry" else "SELL",status=status,original_size=size,size_matched=filled)}
    async def run(self):
        await self.controller.recover()
        return await self.controller.run(order(),exit_price=.49,hold_seconds=0)


@pytest.fixture
def build(tmp_path):
    instances=[]
    def make(mode="full"):
        f=Fixture(tmp_path/(str(len(instances))+".db"),mode);instances.append(f);return f
    yield make
    for f in instances:f.store.close()


def test_full_cycle_requires_remote_flat(build):
    f=build();result=asyncio.run(f.run())
    assert result["phase"]=="CLOSED" and result["bought"]==result["sold"]==10
    assert f.calls==["entry",("exit",10)]
    assert f.store.db.execute("select event from execution_events order by id desc limit 1").fetchone()[0]=="FLAT_VERIFIED"


def test_ambiguous_submit_never_retries(build):
    f=build("ambiguous")
    async def scenario():
        with pytest.raises(ExecutionBlocked,match="ENTRY_ACK_UNKNOWN"):await f.run()
        with pytest.raises(ExecutionBlocked,match="RECOVERY_REQUIRED"):await f.controller.run(order(),exit_price=.49)
        with pytest.raises(ExecutionBlocked,match="RECOVERY_REQUIRED"):await f.controller.recover()
    asyncio.run(scenario())
    assert f.calls==["entry"] and f.store.load()["phase"]=="RECOVERY_REQUIRED"


def test_late_fill_after_cancel_reconciled_before_exit(build):
    f=build("late");result=asyncio.run(f.run())
    assert f.calls==["entry","cancel",("exit",6)]
    assert result["bought"]==result["sold"]==6


def test_partial_exit_blocks_restart_and_next_signal(build):
    f=build("partial_exit")
    async def scenario():
        with pytest.raises(ExecutionBlocked,match="EXIT_INCOMPLETE"):await f.run()
        restarted=ExecutionController(f.store,f,f.account,lambda:f.gate)
        with pytest.raises(ExecutionBlocked,match="RECOVERY_REQUIRED"):await restarted.recover()
        with pytest.raises(ExecutionBlocked):await f.controller.run(order(),exit_price=.49)
    asyncio.run(scenario())
    assert f.store.load()["bought"]-f.store.load()["sold"]==6
    assert f.calls==["entry",("exit",10)]


def test_lookup_failure_persists_recovery(build):
    f=build("inaccessible")
    with pytest.raises(OSError):asyncio.run(f.run())
    assert f.store.load()["phase"]=="RECOVERY_REQUIRED" and f.calls==["entry"]


@pytest.mark.parametrize("field,value",[("open_positions",1),("session_pnl",-25),("geoblock_blocked",None),
    ("connected",False),("book_synced",False),("available_usdc",1),("book_ms",0),("market_slug","other"),
    ("expiry_ms",120999),("signal_valid",False)])
def test_real_gate_values_reject_before_submit(build,field,value):
    f=build();f.gate[field]=value
    with pytest.raises(ExecutionBlocked):asyncio.run(f.run())
    assert f.calls==[] and f.store.load() is None


def test_closed_restart_checks_remote_inventory(build):
    f=build();asyncio.run(f.run())
    async def unknown():return dict(complete=True,observed_ms=1000,open_order_ids=[],balances={"token":1})
    controller=ExecutionController(f.store,f,unknown,lambda:f.gate,clock=lambda:1000)
    with pytest.raises(ExecutionBlocked,match="REMOTE_NOT_FLAT"):asyncio.run(controller.recover())
    assert not controller.reconciled


def test_reservation_is_exclusive_across_connections(build):
    f=build();state={"phase":"ENTRY_SUBMIT_PENDING"}
    f.store.write("INTENT",state,reserve=True)
    with pytest.raises(ExecutionBlocked):f.store.write("INTENT",state,reserve=True)


def test_production_transport_cannot_call_sdk():
    class NoSDK:
        def __getattr__(self,name):raise AssertionError("SDK accessed: "+name)
    transport=LiveClobTransport(NoSDK())
    async def scenario():
        for call in (lambda:transport.submit_limit(order=order()),lambda:transport.submit_exit_limit(token_id="t",price=.5,size=1),lambda:transport.cancel_order(order_id="x")):
            with pytest.raises(RuntimeError,match="USER_APPROVAL_REQUIRED"):await call()
    asyncio.run(scenario())


def test_execution_uses_invariant_guard(build,monkeypatch):
    from app.live.clob_staged import ExecutionInvariantGuard
    seen=[]
    def reject(self,**kwargs):seen.append(kwargs);return {"allow":False,"reasons":["FIXTURE_GATE_REJECT"]}
    monkeypatch.setattr(ExecutionInvariantGuard,"validate_entry",reject)
    f=build()
    with pytest.raises(ExecutionBlocked,match="FIXTURE_GATE_REJECT"):asyncio.run(f.run())
    assert seen and seen[0]["session_pnl"]==f.gate["session_pnl"] and f.calls==[]


def test_submit_timeout_persists_intent_without_resubmit(build):
    f = build()
    async def ambiguous_submit(**kwargs):
        f.calls.append("entry")
        await asyncio.Future()
    f.submit_limit = ambiguous_submit
    async def scenario():
        with pytest.raises(TimeoutError): await f.run()
        assert f.store.load()["phase"] == "RECOVERY_REQUIRED"
        restarted = ExecutionController(f.store, f, f.account, lambda: f.gate)
        with pytest.raises(ExecutionBlocked, match="RECOVERY_REQUIRED"):
            await restarted.recover()
        with pytest.raises(ExecutionBlocked, match="RECOVERY_REQUIRED"):
            await restarted.run(order(), exit_price=.49)
    asyncio.run(scenario())
    assert f.calls == ["entry"]


def test_local_cancellation_during_submit_preserves_ambiguous_remote_state(build):
    f = build()
    async def scenario():
        submitted = asyncio.Event()
        async def ambiguous_submit(**kwargs):
            f.calls.append("entry")
            submitted.set()
            await asyncio.Future()
        f.submit_limit = ambiguous_submit
        task = asyncio.create_task(f.run())
        await asyncio.wait_for(submitted.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert f.store.load()["phase"] == "RECOVERY_REQUIRED"
        with pytest.raises(ExecutionBlocked, match="RECOVERY_REQUIRED"):
            await f.controller.recover()
    asyncio.run(scenario())
    assert f.calls == ["entry"]
