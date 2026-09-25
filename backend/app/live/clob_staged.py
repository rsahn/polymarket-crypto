"""Staged authenticated CLOB boundary for D6.

This module deliberately cannot submit orders. It prepares a live-shaped request
using the installed SDK and returns an audit record. Real submission belongs in
a later, explicitly armed adapter after this staging path is validated.
"""
from __future__ import annotations

import inspect
import math
import os
import time
from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal, ROUND_DOWN


@dataclass(frozen=True)
class StagedLimitOrder:
    signal_id: str
    market_slug: str
    token_id: str
    side: str
    notional: float
    limit_price: float
    size: float
    tick_size: float
    min_order_size: float


def _plain(value):
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


class StagedClobExecutor:
    """Authenticated/live-shaped execution path with a hard no-submit fence."""

    def __init__(self, client):
        self.client = client

    @staticmethod
    def real_orders_enabled() -> bool:
        return os.getenv("REAL_ORDERS_ENABLED", "false").strip().lower() == "true"

    def prepare_buy(self, *, signal_id, market_slug, token_id, notional,
                    best_ask, tick_size, min_order_size, max_slippage_bps=100):
        n = Decimal(str(notional))
        ask = Decimal(str(best_ask))
        tick = Decimal(str(tick_size))
        minimum = Decimal(str(min_order_size))
        slippage = Decimal(str(max_slippage_bps))
        if not all(x.is_finite() for x in (n,ask,tick,minimum,slippage)):
            raise ValueError("non-finite staged inputs")
        if n <= 0 or n > 25 or ask <= 0 or ask >= 1 or tick <= 0 or tick >= 1 or minimum <= 0 or slippage < 0:
            raise ValueError("invalid staged order inputs")
        cap = ask * (Decimal(1) + Decimal(str(max_slippage_bps))/Decimal(10000))
        ticks = (cap/tick).to_integral_value(rounding=ROUND_DOWN)
        price = max(tick, min(Decimal("0.99"), ticks*tick))
        size = (n/price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        if size < Decimal(str(min_order_size)):
            raise ValueError("staged size below market minimum")
        return StagedLimitOrder(
            str(signal_id), str(market_slug), str(token_id), "BUY",
            float(n), float(price), float(size), float(tick), float(min_order_size)
        )

    async def stage(self, order: StagedLimitOrder):
        # Safety invariant: this staging branch must remain incapable of submission.
        forbidden = ("place_limit_order", "place_market_order", "post_order", "post_orders")
        available = [name for name in forbidden if hasattr(self.client, name)]
        return {
            "ts_ms": int(time.time()*1000),
            "mode": "LIVE_STAGING_NO_SUBMIT",
            "real_orders_enabled_env": self.real_orders_enabled(),
            "submit_allowed": False,
            "order": asdict(order),
            "sdk_submission_methods_present": available,
            "sdk_create_limit_order_signature": str(
                inspect.signature(self.client.create_limit_order)
            ) if hasattr(self.client, "create_limit_order") else None,
        }


@dataclass
class SimulatedLifecycle:
    """State machine for exercising ACK/fill/cancel/exit handling with zero submission."""
    state: str = "PREPARED"
    filled_size: float = 0.0
    average_fill_price: float | None = None
    open_size: float = 0.0
    exit_filled_size: float = 0.0
    exit_average_price: float | None = None
    realized_pnl: float = 0.0

    def ack(self):
        if self.state != "PREPARED": raise RuntimeError("ACK_INVALID_STATE")
        self.state = "ACKED"

    def fill(self, *, size: float, price: float, requested_size: float):
        if self.state not in {"ACKED","PARTIAL"}: raise RuntimeError("FILL_INVALID_STATE")
        if size <= 0 or price <= 0 or self.filled_size + size > requested_size + 1e-9:
            raise ValueError("INVALID_FILL")
        previous_cost=(self.average_fill_price or 0.0)*self.filled_size
        self.filled_size += size
        self.average_fill_price=(previous_cost+size*price)/self.filled_size
        self.open_size=self.filled_size
        self.state="FILLED" if self.filled_size >= requested_size-1e-9 else "PARTIAL"

    def cancel(self):
        if self.state not in {"ACKED","PARTIAL"}: raise RuntimeError("CANCEL_INVALID_STATE")
        self.state="CANCELLED_PARTIAL" if self.filled_size else "CANCELLED"

    def exit_fill(self, *, size: float, price: float):
        if self.open_size <= 0 or size <= 0 or size > self.open_size + 1e-9:
            raise ValueError("INVALID_EXIT_FILL")
        previous=self.exit_filled_size
        previous_proceeds=(self.exit_average_price or 0.0)*previous
        self.exit_filled_size += size
        self.exit_average_price=(previous_proceeds+size*price)/self.exit_filled_size
        entry=float(self.average_fill_price or 0.0)
        self.realized_pnl += size*(price-entry)
        self.open_size -= size
        self.state="CLOSED" if self.open_size <= 1e-9 else "EXIT_PARTIAL"

    def snapshot(self):
        return asdict(self)


class KillSwitch:
    def __init__(self, *, max_open_positions=1, max_session_loss=25.0):
        self.max_open_positions=max_open_positions
        self.max_session_loss=max_session_loss

    def check(self, *, open_positions, session_pnl, geoblock_blocked=False,
              market_rotated=False, book_available=True):
        reasons=[]
        if open_positions >= self.max_open_positions: reasons.append("OPEN_POSITION_LIMIT")
        if session_pnl <= -self.max_session_loss: reasons.append("SESSION_LOSS_LIMIT")
        if geoblock_blocked: reasons.append("GEOBLOCK")
        if market_rotated: reasons.append("MARKET_ROTATION")
        if not book_available: reasons.append("BOOK_UNAVAILABLE")
        return {"allow":not reasons,"reasons":reasons}


class LifecycleJournal:
    """Append-only JSONL audit for simulated order lifecycle events."""
    def __init__(self, path):
        from pathlib import Path
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)

    def write(self, *, signal_id, event, lifecycle, details=None):
        import json
        row={
            "ts_ms":int(time.time()*1000),
            "signal_id":str(signal_id),
            "event":str(event),
            "lifecycle":lifecycle.snapshot(),
            "details":details or {},
            "real_orders_enabled":StagedClobExecutor.real_orders_enabled(),
            "submit_allowed":False,
        }
        with self.path.open("a",encoding="utf-8") as fh:
            fh.write(json.dumps(row,sort_keys=True)+"\n")
        return row


async def simulate_lifecycle(*, order: StagedLimitOrder, entry_fill_ratio=1.0,
                             exit_price=None, journal=None):
    """Exercise ACK/fill/partial/cancel/exit deterministically; zero network writes."""
    state=SimulatedLifecycle()
    emit=lambda event,details=None: journal.write(
        signal_id=order.signal_id,event=event,lifecycle=state,details=details
    ) if journal else None
    emit("PREPARED",{"order":asdict(order)})
    state.ack();emit("ACK")
    ratio=max(0.0,min(1.0,float(entry_fill_ratio)))
    fill_size=order.size*ratio
    if fill_size>0:
        state.fill(size=fill_size,price=order.limit_price,requested_size=order.size)
        emit("FILL" if ratio>=1.0 else "PARTIAL_FILL",{"size":fill_size})
    if ratio<1.0:
        state.cancel();emit("CANCEL_REMAINDER")
    if state.open_size>0:
        px=float(exit_price if exit_price is not None else order.limit_price)
        state.exit_fill(size=state.open_size,price=px);emit("EXIT_FILL",{"price":px})
    return state.snapshot()


@dataclass(frozen=True)
class TimeoutPolicy:
    ack_timeout_ms: int = 1500
    fill_timeout_ms: int = 2000
    exit_timeout_ms: int = 2000


class ExecutionInvariantGuard:
    """Fail-closed staging invariants. Pure logic; never touches the network."""
    def __init__(self, policy=TimeoutPolicy()):
        self.policy=policy

    def validate_entry(self, *, open_positions, session_pnl, geoblock_blocked,
                       market_rotated, book_available, seconds_remaining):
        reasons=[]
        if open_positions != 0: reasons.append("POSITION_ALREADY_OPEN")
        if session_pnl <= -25.0: reasons.append("SESSION_LOSS_LIMIT")
        if geoblock_blocked: reasons.append("GEOBLOCK")
        if market_rotated: reasons.append("MARKET_ROTATION")
        if not book_available: reasons.append("BOOK_UNAVAILABLE")
        if seconds_remaining < 120: reasons.append("MARKET_TOO_CLOSE_TO_EXPIRY")
        return {"allow":not reasons,"reasons":reasons}

    def timeout_action(self, *, state, elapsed_ms):
        elapsed=int(elapsed_ms)
        if state=="PREPARED" and elapsed>=self.policy.ack_timeout_ms:
            return "ABORT_NO_ACK"
        if state in {"ACKED","PARTIAL"} and elapsed>=self.policy.fill_timeout_ms:
            return "CANCEL_REMAINDER"
        if state in {"FILLED","CANCELLED_PARTIAL","EXIT_PARTIAL"} and elapsed>=self.policy.exit_timeout_ms:
            return "EXIT_RETRY_OR_KILL"
        return "WAIT"


@dataclass
class BookFreshnessGate:
    """Fail closed after disconnect until a full book sync and fresh update."""
    max_book_age_ms: int = 500
    connected: bool = False
    synced: bool = False
    last_book_update_ms: int | None = None

    def on_disconnect(self):
        self.connected=False;self.synced=False;self.last_book_update_ms=None

    def on_connect(self):
        self.connected=True;self.synced=False;self.last_book_update_ms=None

    def on_book_synced(self, *, initialized, required=2, ts_ms=None):
        self.synced=self.connected and int(initialized)>=int(required)
        if self.synced:self.last_book_update_ms=int(ts_ms if ts_ms is not None else time.time()*1000)

    def on_book_update(self, *, ts_ms=None):
        if self.connected and self.synced:
            self.last_book_update_ms=int(ts_ms if ts_ms is not None else time.time()*1000)

    def status(self, *, now_ms=None):
        now=int(now_ms if now_ms is not None else time.time()*1000)
        reasons=[]
        if not self.connected:reasons.append("WS_DISCONNECTED")
        if not self.synced:reasons.append("BOOK_NOT_SYNCED")
        if self.last_book_update_ms is None:reasons.append("BOOK_TIMESTAMP_MISSING")
        else:
            age=now-self.last_book_update_ms
            if age < 0:reasons.append("BOOK_FROM_FUTURE")
            if age>self.max_book_age_ms:reasons.append("BOOK_STALE")
        return {"allow":not reasons,"reasons":reasons,
                "book_age_ms":None if self.last_book_update_ms is None else max(0,now-self.last_book_update_ms)}


class SimulatedCycleError(RuntimeError):
    pass

class SimulatedNightCycle:
    """Deterministic fail-closed controller for unattended lifecycle testing."""
    def __init__(self, *, hold_ms=500):
        self.hold_ms=int(hold_ms)

    def run(self, *, requested_size, entry_fills, exit_fills):
        life=SimulatedLifecycle();events=[]
        def snap(name):
            events.append({"event":name,**life.snapshot()})
        snap("PREPARED");life.ack();snap("ACK")
        for size,price in entry_fills:
            life.fill(size=float(size),price=float(price),requested_size=float(requested_size))
            snap("FILL" if life.state=="FILLED" else "PARTIAL_FILL")
        if life.state in {"ACKED","PARTIAL"}:
            life.cancel();snap("CANCEL_REMAINDER")
        if life.open_size<=0:
            raise SimulatedCycleError("ENTRY_NOT_FILLED")
        # hold_ms is recorded by policy; tests stay deterministic and do not sleep.
        events.append({"event":"HOLD","hold_ms":self.hold_ms})
        for size,price in exit_fills:
            life.exit_fill(size=float(size),price=float(price));snap("EXIT_FILL")
        if life.open_size>1e-9:
            raise SimulatedCycleError(f"POSITION_NOT_FLAT:{life.open_size}")
        if life.state!="CLOSED":
            raise SimulatedCycleError("CYCLE_NOT_CLOSED")
        return {"state":"CLOSED","events":events,"final":life.snapshot()}


@dataclass
class PersistedPositionState:
    """Crash-recovery state. No transport calls; safe for staging/tests."""
    signal_id: str
    market_slug: str
    token_id: str
    state: str = "PREPARED"
    entry_order_id: str | None = None
    exit_order_id: str | None = None
    filled_shares: float = 0.0
    sold_shares: float = 0.0
    updated_ms: int = 0

    @property
    def open_shares(self):
        return max(0.0,self.filled_shares-self.sold_shares)

class PositionStateStore:
    def __init__(self,path):
        from pathlib import Path
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)

    def save(self,state):
        import json,os,tempfile
        state.updated_ms=int(time.time()*1000)
        payload=asdict(state)
        tmp=self.path.with_suffix(self.path.suffix+".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload,sort_keys=True,indent=2,allow_nan=False))
            fh.flush();os.fsync(fh.fileno())
        os.replace(tmp,self.path)
        return payload

    def load(self):
        import json
        if not self.path.exists():return None
        return PersistedPositionState(**json.loads(self.path.read_text(encoding="utf-8")))

    def assert_flat_or_recover(self):
        state=self.load()
        return {"allow_new_entry":False,"reason":"REMOTE_RECONCILIATION_REQUIRED",
                "state":None if state is None else asdict(state)}


class RecoveryReconciler:
    """Reconcile persisted state with a read-only CLOB order lookup.

    This class never submits or cancels. Unknown remote state fails closed.
    """
    def __init__(self, client):
        self.client=client

    async def reconcile(self, state):
        if state is None:
            return {"allow_new_entry":False,"reason":"REMOTE_RECONCILIATION_REQUIRED"}
        order_id=state.exit_order_id or state.entry_order_id
        if not order_id:
            return {"allow_new_entry":False,"reason":"ORDER_ID_MISSING"}
        try:
            remote=await self.client.get_order(order_id=str(order_id))
        except Exception as exc:
            return {"allow_new_entry":False,"reason":"RECOVERY_REQUIRED",
                    "cause":"REMOTE_LOOKUP_FAILED","error_type":type(exc).__name__}
        data=_plain(remote)
        return {"allow_new_entry":False,"reason":"REMOTE_REVIEW_REQUIRED",
                "order_id":str(order_id),"remote":data,"local":asdict(state)}


class RemoteStateProjector:
    """Project normalized read-only CLOB status into persisted local state."""
    TERMINAL_CANCEL={"CANCELLED","CANCELED","EXPIRED"}
    FULL={"FILLED","MATCHED"}

    def apply(self, state, normalized, *, leg="entry"):
        if not normalized or not normalized.get("known"):
            return {"ok":False,"reason":"UNKNOWN_REMOTE_STATUS","state":state}
        status=normalized.get("status")
        if status not in self.FULL | self.TERMINAL_CANCEL | {"LIVE","OPEN","PENDING"}:
            return {"ok":False,"reason":"UNMAPPED_REMOTE_STATUS","state":state}
        try:
            filled=float(normalized["filled_size"]);original=float(normalized["original_size"])
            previous=state.sold_shares if leg=="exit" else state.filled_shares
            if leg not in {"entry","exit"} or not all(math.isfinite(x) for x in (filled,original,previous)):
                raise ValueError()
            if original<=0 or filled<previous or filled>original or filled<0:raise ValueError()
            if status in self.FULL and filled!=original:raise ValueError()
            if leg=="exit" and filled>state.filled_shares:raise ValueError()
        except (KeyError,TypeError,ValueError,OverflowError):
            return {"ok":False,"reason":"INVALID_REMOTE_SIZES","state":state}
        if leg=="exit":
            state.sold_shares=filled
            state.state="FLAT_PENDING_VERIFICATION" if state.open_shares==0 else "EXIT_PARTIAL"
        else:
            state.filled_shares=filled
            if status in self.TERMINAL_CANCEL:
                state.state="CANCELLED_PARTIAL" if filled else "CANCELLED"
            elif status in self.FULL:state.state="FILLED"
            else:state.state="PARTIAL" if filled else "ACKED"
        state.updated_ms=int(time.time()*1000)
        return {"ok":True,"reason":"PROJECTED","state":state}



class ReadOnlyPositionSynchronizer:
    """Read get_order(), normalize/project it, then atomically persist local state.

    No create/post/cancel methods are called.
    """
    def __init__(self, client, store):
        self.client=client;self.store=store;self.projector=RemoteStateProjector()

    async def sync(self, state):
        from .clob_transport import normalize_order_status
        order_id=state.exit_order_id or state.entry_order_id
        if not order_id:
            return {"ok":False,"reason":"ORDER_ID_MISSING"}
        try:
            raw=await self.client.get_order(order_id=str(order_id))
        except Exception as exc:
            return {"ok":False,"reason":"GET_ORDER_FAILED","error":f"{type(exc).__name__}:{exc}"}
        normalized=normalize_order_status({"response":_plain(raw)})
        projected=self.projector.apply(state,normalized,leg="exit" if state.exit_order_id else "entry")
        if not projected.get("ok"):
            return {"ok":False,"reason":projected.get("reason"),"normalized":normalized}
        saved=self.store.save(state)
        return {"ok":True,"reason":"SYNCED_AND_PERSISTED","normalized":normalized,"state":saved}
