import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at_ms INTEGER NOT NULL,
    initial_equity REAL NOT NULL,
    shadow INTEGER NOT NULL,
    champion_name TEXT NOT NULL,
    champion_version TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    market_id TEXT NOT NULL,
    market_duration TEXT NOT NULL,
    btc_price REAL,
    up_bid REAL,
    up_ask REAL,
    down_bid REAL,
    down_ask REAL,
    up_depth REAL,
    down_depth REAL,
    rule TEXT NOT NULL,
    expected_pair_cost REAL,
    expected_edge REAL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    feed_age_ms INTEGER,
    processing_latency_ms INTEGER,
    decision_latency_ms INTEGER,
    simulated_execution_latency_ms INTEGER
);
CREATE TABLE IF NOT EXISTS paper_equity (
    equity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    exposure REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paper_decisions_session_ts ON paper_decisions(session_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_paper_equity_session_ts ON paper_equity(session_id, timestamp_ms);
"""


@dataclass(frozen=True)
class ChampionV1:
    name: str
    version: str
    rules_loaded: bool
    reason: str

    @property
    def validated(self) -> bool:
        return self.rules_loaded and self.name != "NONE"

    @classmethod
    def load(cls, path: Path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            return cls("NONE", "missing", False, f"champion artifact unavailable: {exc}")
        name = str(payload.get("champion") or "NONE")
        return cls(name, str(payload.get("version") or "d2"), name != "NONE", str(payload.get("reason") or ""))


class PaperAudit:
    def __init__(self, path: Path, initial_equity: float, shadow: bool, champion: ChampionV1):
        self.path = path
        self.initial_equity = initial_equity
        self.shadow = shadow
        self.champion = champion
        self.session_id = None

    async def init(self, started_at_ms: int):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            cursor = await db.execute(
                """INSERT INTO paper_sessions(started_at_ms,initial_equity,shadow,champion_name,champion_version,status)
                   VALUES(?,?,?,?,?,?)""",
                (started_at_ms, self.initial_equity, int(self.shadow), self.champion.name, "d2", "RUNNING"),
            )
            self.session_id = cursor.lastrowid
            await db.execute(
                """INSERT INTO paper_equity(session_id,timestamp_ms,equity,cash,exposure,realized_pnl,unrealized_pnl)
                   VALUES(?,?,?,?,?,?,?)""",
                (self.session_id, started_at_ms, self.initial_equity, self.initial_equity, 0.0, 0.0, 0.0),
            )
            await db.commit()

    async def record_snapshot(self, snapshot: dict[str, Any], btc_price: float | None, now_ms: int):
        if self.session_id is None:
            raise RuntimeError("PaperAudit is not initialized")
        up = snapshot.get("up") or {}
        down = snapshot.get("down") or {}
        reason = "CHAMPION_NOT_VALIDATED" if not self.champion.validated else "SHADOW_ONLY"
        decision = "NO_TRADE"
        event_ts = snapshot.get("event_ts_ms")
        feed_age = now_ms - event_ts if event_ts else None
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO paper_decisions(
                    session_id,timestamp_ms,market_id,market_duration,btc_price,up_bid,up_ask,down_bid,down_ask,
                    up_depth,down_depth,rule,expected_pair_cost,expected_edge,decision,reason,feed_age_ms,
                    processing_latency_ms,decision_latency_ms,simulated_execution_latency_ms)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.session_id, now_ms, snapshot.get("market_key", "unknown"), snapshot.get("market_key", "unknown"),
                 btc_price, up.get("bid"), up.get("ask"), down.get("bid"), down.get("ask"),
                 up.get("ask_qty"), down.get("ask_qty"), self.champion.name, None, None, decision, reason,
                 feed_age, 0, 0, 0),
            )
            await db.execute(
                """INSERT INTO paper_equity(session_id,timestamp_ms,equity,cash,exposure,realized_pnl,unrealized_pnl)
                   VALUES(?,?,?,?,?,?,?)""",
                (self.session_id, now_ms, self.initial_equity, self.initial_equity, 0.0, 0.0, 0.0),
            )
            await db.commit()
