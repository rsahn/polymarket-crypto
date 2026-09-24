import asyncio
from app.live.clob_staged import StagedLimitOrder
from app.live.real_scaffold import LiveArmGate,RealExecutionScaffold

def order(n=5):
 return StagedLimitOrder("s","slug","token","BUY",n,.5,n/.5,.01,5)

def test_gate_requires_double_arm_and_token(monkeypatch):
 g=LiveArmGate()
 assert not g.status(session_token="x")["armed"]
 monkeypatch.setenv("REAL_ORDERS_ENABLED","true")
 monkeypatch.setenv("LIVE_EXECUTION_ARMED","true")
 monkeypatch.setenv("LIVE_SESSION_TOKEN","secret")
 assert not g.status(session_token="wrong")["armed"]
 assert g.status(session_token="secret")["armed"]

def test_scaffold_still_cannot_submit(monkeypatch):
 monkeypatch.setenv("REAL_ORDERS_ENABLED","true");monkeypatch.setenv("LIVE_EXECUTION_ARMED","true");monkeypatch.setenv("LIVE_SESSION_TOKEN","secret")
 x=RealExecutionScaffold(object())
 prepared=asyncio.run(x.prepare(order=order(),session_token="secret"))
 assert prepared["ready_for_transport"] is True
 assert prepared["submit_allowed"] is False
 try:asyncio.run(x.submit(order()))
 except RuntimeError as exc:assert str(exc)=="LIVE_TRANSPORT_NOT_WIRED"
 else:assert False

def test_notional_cap(monkeypatch):
 monkeypatch.setenv("REAL_ORDERS_ENABLED","true");monkeypatch.setenv("LIVE_EXECUTION_ARMED","true");monkeypatch.setenv("LIVE_SESSION_TOKEN","secret")
 x=RealExecutionScaffold(object())
 prepared=asyncio.run(x.prepare(order=order(30),session_token="secret"))
 assert not prepared["ready_for_transport"]
 assert "NOTIONAL_ABOVE_MAX" in prepared["reasons"]
