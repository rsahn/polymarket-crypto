"""Real-execution adapter scaffold.

IMPORTANT: submission is intentionally NOT wired. This module prepares the
two-key arming contract and validates risk state so the live transport can be
reviewed separately before any money can move.
"""
from __future__ import annotations
import os,time
from dataclasses import asdict,dataclass

@dataclass(frozen=True)
class LiveArmConfig:
    max_notional: float = 25.0
    smoke_notional: float = 5.0
    max_open_positions: int = 1
    session_loss_limit: float = 25.0

class LiveArmGate:
    """Requires two independent opt-ins and an exact session token."""
    def __init__(self, config=LiveArmConfig()):
        self.config=config

    def status(self, *, session_token=None, open_positions=0, session_pnl=0.0,
               geoblock_blocked=False, market_rotated=False, book_available=True):
        reasons=[]
        if os.getenv("REAL_ORDERS_ENABLED","false").lower()!="true":
            reasons.append("REAL_ORDERS_DISABLED")
        if os.getenv("LIVE_EXECUTION_ARMED","false").lower()!="true":
            reasons.append("LIVE_EXECUTION_NOT_ARMED")
        expected=os.getenv("LIVE_SESSION_TOKEN")
        if not expected or not session_token or session_token!=expected:
            reasons.append("SESSION_TOKEN_MISMATCH")
        if open_positions>=self.config.max_open_positions:
            reasons.append("OPEN_POSITION_LIMIT")
        if session_pnl<=-self.config.session_loss_limit:
            reasons.append("SESSION_LOSS_LIMIT")
        if geoblock_blocked:reasons.append("GEOBLOCK")
        if market_rotated:reasons.append("MARKET_ROTATION")
        if not book_available:reasons.append("BOOK_UNAVAILABLE")
        return {"armed":not reasons,"reasons":reasons}

class RealExecutionScaffold:
    """Fail-closed API: even an armed gate cannot submit in this revision."""
    def __init__(self, client, gate=None):
        self.client=client;self.gate=gate or LiveArmGate()

    async def prepare(self, *, order, session_token=None, open_positions=0,
                      session_pnl=0.0, geoblock_blocked=False,
                      market_rotated=False, book_available=True):
        gate=self.gate.status(session_token=session_token,open_positions=open_positions,
          session_pnl=session_pnl,geoblock_blocked=geoblock_blocked,
          market_rotated=market_rotated,book_available=book_available)
        notional=float(order.notional)
        reasons=list(gate["reasons"])
        if notional>self.gate.config.max_notional:reasons.append("NOTIONAL_ABOVE_MAX")
        return {"ts_ms":int(time.time()*1000),"gate":gate,"order":asdict(order),
                "ready_for_transport":not reasons,"reasons":reasons,
                "submit_allowed":False,"status":"LIVE_TRANSPORT_NOT_WIRED"}

    async def submit(self, *args, **kwargs):
        raise RuntimeError("LIVE_TRANSPORT_NOT_WIRED")
