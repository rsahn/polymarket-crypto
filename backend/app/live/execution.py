"""Deterministic execution protocol. Production monetary transport stays locked.

The injected account reader must supply complete, authenticated account evidence;
a missing capability is a rejection, never an inferred empty account.
"""
from __future__ import annotations
import asyncio
import json
import math
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from .clob_transport import extract_order_id, normalize_order_status
from .clob_staged import ExecutionInvariantGuard


class ExecutionBlocked(RuntimeError):
    pass


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ExecutionBlocked("INVALID_NUMBER")
    return value


class ExecutionStore:
    """Snapshot and append-only transitions commit in the same durable transaction."""
    def __init__(self, path):
        self.db = sqlite3.connect(Path(path), isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS execution_state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS execution_events (id INTEGER PRIMARY KEY, ts_ms INTEGER NOT NULL, event TEXT NOT NULL, value TEXT NOT NULL)")

    def load(self):
        row = self.db.execute("SELECT value FROM execution_state WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None

    def write(self, event, state, *, reserve=False):
        payload = json.dumps(state, sort_keys=True, allow_nan=False)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.load()
            if reserve and previous and previous["phase"] != "CLOSED":
                raise ExecutionBlocked("POSITION_OR_RECOVERY_PENDING")
            self.db.execute("INSERT INTO execution_events(ts_ms,event,value) VALUES(?,?,?)", (int(time.time()*1000),event,payload))
            self.db.execute("INSERT INTO execution_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (payload,))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()


class ExecutionController:
    def __init__(self, store, transport, account_reader, gate_reader, *, timeout=2.0, clock=None):
        self.store, self.transport = store, transport
        self.account_reader, self.gate_reader = account_reader, gate_reader
        if not math.isfinite(timeout) or timeout <= 0: raise ValueError("timeout")
        self.timeout = timeout
        self.clock = clock or (lambda: int(time.time()*1000))
        self.lock = asyncio.Lock()
        self.reconciled = False

    async def account(self):
        evidence = await asyncio.wait_for(self.account_reader(), self.timeout)
        if not isinstance(evidence, dict) or evidence.get("complete") is not True:
            raise ExecutionBlocked("ACCOUNT_EVIDENCE_INCOMPLETE")
        age = self.clock()-finite(evidence.get("observed_ms"))
        if age < 0 or age > 500: raise ExecutionBlocked("ACCOUNT_EVIDENCE_STALE")
        orders, balances = evidence.get("open_order_ids"), evidence.get("balances")
        if not isinstance(orders,list) or not isinstance(balances,dict):
            raise ExecutionBlocked("ACCOUNT_EVIDENCE_INVALID")
        if orders: raise ExecutionBlocked("REMOTE_ORDERS_OPEN")
        for quantity in balances.values():
            if finite(quantity) < 0: raise ExecutionBlocked("NEGATIVE_INVENTORY")
        return evidence

    @staticmethod
    def flat(evidence):
        if any(q != 0 for q in evidence["balances"].values()):
            raise ExecutionBlocked("REMOTE_NOT_FLAT")

    async def recover(self):
        async with self.lock:
            self.reconciled = False
            state = self.store.load()
            # Ambiguous submission IDs cannot safely be guessed or resubmitted.
            if state and state["phase"] != "CLOSED":
                raise ExecutionBlocked("RECOVERY_REQUIRED")
            self.flat(await self.account())
            self.reconciled = True

    def gates(self, order):
        gate = self.gate_reader()
        if not isinstance(gate,dict): raise ExecutionBlocked("GATES_MISSING")
        for name in ("connected", "book_synced", "signal_valid", "recovery_complete"):
            if gate.get(name) is not True: raise ExecutionBlocked(name.upper())
        if gate.get("geoblock_blocked") is not False: raise ExecutionBlocked("GEOBLOCK_UNKNOWN_OR_BLOCKED")
        if gate.get("market_slug") != order.market_slug or gate.get("token_id") != order.token_id:
            raise ExecutionBlocked("MARKET_ROTATION")
        now = self.clock()
        for name in ("book_ms", "risk_ms", "signal_ms", "geo_ms"):
            age = now-finite(gate.get(name))
            if age < 0 or age > 500: raise ExecutionBlocked("STALE_"+name.upper())
        invariant = ExecutionInvariantGuard().validate_entry(
            open_positions=gate.get("open_positions"), session_pnl=finite(gate.get("session_pnl")),
            geoblock_blocked=gate.get("geoblock_blocked"),
            market_rotated=gate.get("market_slug") != order.market_slug,
            book_available=gate.get("connected") is True and gate.get("book_synced") is True,
            seconds_remaining=(finite(gate.get("expiry_ms"))-now)/1000)
        if not invariant["allow"]: raise ExecutionBlocked(",".join(invariant["reasons"]))
        if finite(gate.get("session_pnl")) <= -25: raise ExecutionBlocked("SESSION_LOSS_LIMIT")
        if gate.get("open_positions") != 0: raise ExecutionBlocked("POSITION_ALREADY_OPEN")
        if finite(gate.get("available_usdc")) < order.notional: raise ExecutionBlocked("INSUFFICIENT_BANKROLL")
        if not (0 < finite(order.notional) <= 25 and 0 < finite(order.limit_price) < 1 and finite(order.size) > 0):
            raise ExecutionBlocked("INVALID_ORDER")
        if order.side != "BUY" or order.size*order.limit_price > order.notional+1e-9:
            raise ExecutionBlocked("INVALID_ORDER_COST")
        if finite(gate.get("fillable_shares")) < order.size: raise ExecutionBlocked("INSUFFICIENT_DEPTH")
        return gate

    async def status(self, state, leg):
        event = await asyncio.wait_for(self.transport.get_order(order_id=state[leg+"_id"]), self.timeout)
        value = normalize_order_status(event)
        if not value.get("known"): raise ExecutionBlocked("UNKNOWN_REMOTE_STATUS")
        response = event["response"]
        if extract_order_id(event) != state[leg+"_id"]: raise ExecutionBlocked("ORDER_ID_MISMATCH")
        if str(response.get("asset_id", response.get("token_id", ""))) != state["order"]["token_id"]:
            raise ExecutionBlocked("TOKEN_MISMATCH")
        if response.get("side") != ("BUY" if leg=="entry" else "SELL"): raise ExecutionBlocked("SIDE_MISMATCH")
        expected = state["order"]["size"] if leg=="entry" else state["exit_size"]
        if value["original_size"] != expected: raise ExecutionBlocked("ORDER_SIZE_MISMATCH")
        key = "bought" if leg=="entry" else "sold"
        if value["filled_size"] < state[key]: raise ExecutionBlocked("FILL_REGRESSION")
        state[key] = value["filled_size"]
        state[leg+"_status"] = value["status"]
        self.store.write(leg.upper()+"_STATUS",state)
        return value

    async def settle(self, state, leg):
        deadline = time.monotonic()+self.timeout
        terminal = {"FILLED","MATCHED","CANCELLED","CANCELED","EXPIRED"}
        while True:
            value = await self.status(state, leg)
            if value["status"] in terminal: return
            if time.monotonic() >= deadline: break
            await asyncio.sleep(.01)
        state["phase"] = leg.upper()+"_CANCEL_PENDING"
        self.store.write("CANCEL_INTENT",state)
        await asyncio.wait_for(self.transport.cancel_order(order_id=state[leg+"_id"]),self.timeout)
        # A cancellation ACK alone never establishes final filled quantity.
        value = await self.status(state,leg)
        if value["status"] not in terminal: raise ExecutionBlocked("CANCEL_UNCONFIRMED")

    async def run(self, order, *, exit_price, hold_seconds=.5):
        if self.lock.locked(): raise ExecutionBlocked("POSITION_ALREADY_OPEN")
        async with self.lock:
            if not self.reconciled: raise ExecutionBlocked("RECOVERY_REQUIRED")
            if not 0 < finite(exit_price) < 1: raise ExecutionBlocked("INVALID_EXIT_PRICE")
            if finite(hold_seconds) < 0: raise ExecutionBlocked("INVALID_HOLD")
            self.gates(order)
            self.flat(await self.account())
            self.gates(order)  # Revalidate after awaited account read.
            state = {"phase":"ENTRY_SUBMIT_PENDING","order":asdict(order),"entry_id":None,"exit_id":None,
                     "bought":0.0,"sold":0.0,"exit_size":0.0}
            self.store.write("ENTRY_INTENT",state,reserve=True)
            self.reconciled = False
            try:
                event = await asyncio.wait_for(self.transport.submit_limit(order=order),self.timeout)
                state["entry_id"] = extract_order_id(event)
                if not state["entry_id"]: raise ExecutionBlocked("ENTRY_ACK_UNKNOWN")
                state["phase"] = "ENTRY_ACKED"
                self.store.write("ENTRY_ACK",state)
                await self.settle(state,"entry")
                evidence = await self.account()
                if evidence["balances"].get(order.token_id,0) != state["bought"]:
                    raise ExecutionBlocked("ENTRY_INVENTORY_MISMATCH")
                if any(q != 0 for token,q in evidence["balances"].items() if token != order.token_id):
                    raise ExecutionBlocked("UNEXPECTED_INVENTORY")
                if state["bought"]:
                    await asyncio.sleep(hold_seconds)
                    gate = self.gate_reader()
                    if gate.get("connected") is not True or gate.get("book_synced") is not True:
                        raise ExecutionBlocked("EXIT_BOOK_UNAVAILABLE")
                    if gate.get("market_slug") != order.market_slug or gate.get("token_id") != order.token_id:
                        raise ExecutionBlocked("EXIT_MARKET_ROTATION")
                    age=self.clock()-finite(gate.get("book_ms"))
                    if age<0 or age>500:raise ExecutionBlocked("EXIT_BOOK_STALE")
                    state["exit_size"] = state["bought"]
                    state["phase"] = "EXIT_SUBMIT_PENDING"
                    self.store.write("EXIT_INTENT",state)
                    event = await asyncio.wait_for(self.transport.submit_exit_limit(token_id=order.token_id,price=exit_price,size=state["exit_size"]),self.timeout)
                    state["exit_id"] = extract_order_id(event)
                    if not state["exit_id"]: raise ExecutionBlocked("EXIT_ACK_UNKNOWN")
                    state["phase"] = "EXIT_ACKED"
                    self.store.write("EXIT_ACK",state)
                    await self.settle(state,"exit")
                    if state["sold"] != state["bought"]: raise ExecutionBlocked("EXIT_INCOMPLETE")
                self.flat(await self.account())
                state["phase"] = "CLOSED"
                self.store.write("FLAT_VERIFIED",state)
                self.reconciled = True
                return state
            except BaseException as exc:
                state["phase"] = "RECOVERY_REQUIRED"
                state["error_type"] = type(exc).__name__
                self.store.write("FAIL_CLOSED",state)
                raise
