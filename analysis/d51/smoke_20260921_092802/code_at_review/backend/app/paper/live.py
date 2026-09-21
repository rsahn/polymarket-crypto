import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from app.paper.executor import PaperExecutor, PaperTrade


SCHEMA = '''
CREATE TABLE IF NOT EXISTS paper_sessions (
 session_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at_ms INTEGER NOT NULL,
 initial_equity REAL NOT NULL, shadow INTEGER NOT NULL, champion_name TEXT NOT NULL,
 champion_version TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_decisions (
 decision_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
 timestamp_ms INTEGER NOT NULL, market_id TEXT NOT NULL, market_duration TEXT NOT NULL,
 btc_price REAL, up_bid REAL, up_ask REAL, down_bid REAL, down_ask REAL,
 up_depth REAL, down_depth REAL, rule TEXT NOT NULL, expected_pair_cost REAL,
 expected_edge REAL, decision TEXT NOT NULL, reason TEXT NOT NULL, feed_age_ms INTEGER,
 processing_latency_ms INTEGER, decision_latency_ms INTEGER, simulated_execution_latency_ms INTEGER);
CREATE TABLE IF NOT EXISTS paper_equity (
 equity_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
 timestamp_ms INTEGER NOT NULL, equity REAL NOT NULL, cash REAL NOT NULL,
 exposure REAL NOT NULL, realized_pnl REAL NOT NULL, unrealized_pnl REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paper_trades (
 trade_pk INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
 trade_id TEXT NOT NULL, market_id TEXT NOT NULL, market_duration TEXT NOT NULL,
 strategy TEXT NOT NULL, opened_at_ms INTEGER NOT NULL, closed_at_ms INTEGER,
 status TEXT NOT NULL, hedge_status TEXT NOT NULL, up_qty REAL NOT NULL,
 down_qty REAL NOT NULL, paired_qty REAL NOT NULL, unhedged_qty REAL NOT NULL,
 up_cost REAL NOT NULL, down_cost REAL NOT NULL, fees REAL NOT NULL,
 slippage_cost REAL NOT NULL, gross_pnl REAL NOT NULL, net_pnl REAL NOT NULL,
 hedge_eligible_at_ms INTEGER, hedge_deadline_ms INTEGER, first_side TEXT,
 UNIQUE(session_id, trade_id));
CREATE TABLE IF NOT EXISTS paper_fills (
 fill_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
 trade_id TEXT NOT NULL, timestamp_ms INTEGER NOT NULL, leg INTEGER NOT NULL,
 side TEXT NOT NULL, requested_qty REAL NOT NULL, filled_qty REAL NOT NULL,
 observed_ask REAL NOT NULL, fill_price REAL NOT NULL, notional REAL NOT NULL,
 fee REAL NOT NULL, slippage_per_contract REAL NOT NULL, slippage_cost REAL NOT NULL,
 partial INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_paper_decisions_session_ts ON paper_decisions(session_id,timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_paper_equity_session_ts ON paper_equity(session_id,timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_paper_trades_session_trade ON paper_trades(session_id,trade_id);
CREATE INDEX IF NOT EXISTS idx_paper_fills_session_trade ON paper_fills(session_id,trade_id);
'''


@dataclass(frozen=True)
class ChampionV1:
    name: str
    version: str
    rules_loaded: bool
    reason: str

    @property
    def validated(self):
        return self.rules_loaded and self.name != "NONE"

    @classmethod
    def load(cls, path: Path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            return cls("NONE", "missing", False, f"champion artifact unavailable: {exc}")
        name = str(payload.get("champion") or "NONE")
        return cls(name, str(payload.get("version") or "d2"), name != "NONE",
                   str(payload.get("reason") or ""))


class PaperAudit:
    def __init__(self, path: Path, initial_equity: float, shadow: bool, champion: ChampionV1,
                 *, fee_rate=0.0, slippage=0.0, max_unhedged=2.0):
        self.path = path
        self.initial_equity = float(initial_equity)
        self.shadow = bool(shadow)
        self.champion = champion
        self.session_id: Optional[int] = None
        self.executor = PaperExecutor(self.initial_equity, max_unhedged, fee_rate, slippage)
        self.trades: dict[str, PaperTrade] = {}
        self.realized_pnl = 0.0
        self.hedge_min_delay_ms = 15_000
        self.hedge_max_delay_ms = 30_000

    @property
    def cash(self):
        return self.executor.cash

    @property
    def exposure(self):
        return sum(t.unhedged_qty for t in self.trades.values() if t.status == "OPEN")

    @property
    def equity(self):
        paired_value = sum(t.paired_qty for t in self.trades.values() if t.status == "OPEN")
        return self.cash + paired_value

    async def init(self, started_at_ms: int):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            # Backward-compatible migration for existing paper_live.db files.
            cols = {row[1] for row in await (await db.execute("PRAGMA table_info(paper_trades)")).fetchall()}
            for name, ddl in (
                ("hedge_eligible_at_ms", "INTEGER"),
                ("hedge_deadline_ms", "INTEGER"),
                ("first_side", "TEXT"),
            ):
                if name not in cols:
                    await db.execute(f"ALTER TABLE paper_trades ADD COLUMN {name} {ddl}")
            cur = await db.execute(
                "INSERT INTO paper_sessions(started_at_ms,initial_equity,shadow,champion_name,champion_version,status) VALUES(?,?,?,?,?,?)",
                (started_at_ms,self.initial_equity,int(self.shadow),self.champion.name,self.champion.version,"RUNNING"))
            self.session_id = cur.lastrowid
            await self._record_equity(db, started_at_ms)
            await db.commit()

    async def _record_equity(self, db, now_ms):
        await db.execute(
            "INSERT INTO paper_equity(session_id,timestamp_ms,equity,cash,exposure,realized_pnl,unrealized_pnl) VALUES(?,?,?,?,?,?,?)",
            (self.session_id,now_ms,self.equity,self.cash,self.exposure,self.realized_pnl,0.0))

    async def record_snapshot(self, snapshot: dict[str, Any], btc_price: float | None, now_ms: int):
        if self.session_id is None:
            raise RuntimeError("PaperAudit is not initialized")
        up, down = snapshot.get("up") or {}, snapshot.get("down") or {}
        ua, da = up.get("ask"), down.get("ask")
        pair_cost = float(ua)+float(da) if ua is not None and da is not None else None
        edge = 1.0-pair_cost if pair_cost is not None else None
        reason = "CHAMPION_NOT_VALIDATED" if not self.champion.validated else "SHADOW_ONLY"
        event_ts = snapshot.get("event_ts_ms")
        feed_age = max(0,now_ms-event_ts) if event_ts else None
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''INSERT INTO paper_decisions(session_id,timestamp_ms,market_id,market_duration,btc_price,
                up_bid,up_ask,down_bid,down_ask,up_depth,down_depth,rule,expected_pair_cost,expected_edge,
                decision,reason,feed_age_ms,processing_latency_ms,decision_latency_ms,simulated_execution_latency_ms)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (self.session_id,now_ms,snapshot.get("market_key","unknown"),snapshot.get("market_key","unknown"),
                 btc_price,up.get("bid"),ua,down.get("bid"),da,up.get("ask_qty"),down.get("ask_qty"),
                 self.champion.name,pair_cost,edge,"NO_TRADE",reason,feed_age,0,0,0))
            await self._record_equity(db, now_ms)
            await db.commit()

    async def execute_pair(self, *, trade_id, market_id, market_duration, strategy, now_ms,
                           up_ask, up_ask_qty, down_ask, down_ask_qty, requested_qty,
                           experimental=False):
        if self.session_id is None:
            raise RuntimeError("PaperAudit is not initialized")
        if not self.champion.validated and not experimental:
            return None
        if trade_id in self.trades:
            raise ValueError(f"duplicate trade_id: {trade_id}")

        trade = PaperTrade(trade_id,market_id,market_duration,strategy,int(now_ms))
        self.trades[trade_id] = trade

        leg1 = self.executor.simulate_buy(
            trade_id=trade_id,leg=1,side="UP",ask=up_ask,ask_qty=up_ask_qty,
            requested_qty=requested_qty,timestamp_ms=now_ms)
        if leg1:
            self.executor.apply_fill(trade, leg1)

        # Hedge only the actually filled first-leg quantity.
        hedge_qty = trade.up_qty
        leg2 = None
        if hedge_qty > 0:
            leg2 = self.executor.simulate_buy(
                trade_id=trade_id,leg=2,side="DOWN",ask=down_ask,ask_qty=down_ask_qty,
                requested_qty=hedge_qty,timestamp_ms=now_ms)
            if leg2:
                self.executor.apply_fill(trade, leg2)

        if trade.paired_qty > 0 and trade.unhedged_qty <= 1e-9:
            trade.status = "HEDGED"
        elif trade.paired_qty > 0:
            trade.status = "PARTIAL_HEDGE"
        elif trade.up_qty > 0:
            trade.status = "UNHEDGED"
        else:
            trade.status = "NO_FILL"

        async with aiosqlite.connect(self.path) as db:
            for fill in trade.fills:
                await db.execute(
                    '''INSERT INTO paper_fills(session_id,trade_id,timestamp_ms,leg,side,requested_qty,
                    filled_qty,observed_ask,fill_price,notional,fee,slippage_per_contract,slippage_cost,partial)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (self.session_id,fill.trade_id,fill.timestamp_ms,fill.leg,fill.side,fill.requested_qty,
                     fill.filled_qty,fill.observed_ask,fill.price,fill.notional,fill.fee,
                     fill.slippage_per_contract,fill.slippage_cost,int(fill.partial)))
            await db.execute(
                '''INSERT INTO paper_trades(session_id,trade_id,market_id,market_duration,strategy,opened_at_ms,
                closed_at_ms,status,hedge_status,up_qty,down_qty,paired_qty,unhedged_qty,up_cost,down_cost,
                fees,slippage_cost,gross_pnl,net_pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (self.session_id,trade.trade_id,trade.market_id,trade.market_duration,trade.strategy,
                 trade.opened_at_ms,trade.closed_at_ms,trade.status,trade.hedge_status,trade.up_qty,
                 trade.down_qty,trade.paired_qty,trade.unhedged_qty,trade.up_cost,trade.down_cost,
                 trade.fees,trade.slippage_cost,trade.gross_pnl_if_settled,trade.net_pnl_if_settled))
            await self._record_equity(db, now_ms)
            await db.commit()
        return trade


    async def open_temporal_trade(
        self, *, trade_id, market_id, market_duration, strategy, now_ms,
        first_side, ask, ask_qty, requested_qty, experimental=False
    ):
        """Open LEG 1 only. C3 hedge becomes eligible at +15s and expires at +30s."""
        if self.session_id is None:
            raise RuntimeError("PaperAudit is not initialized")
        if not self.champion.validated and not experimental:
            return None
        if trade_id in self.trades:
            raise ValueError(f"duplicate trade_id: {trade_id}")

        first_side = str(first_side).upper()
        if first_side not in ("UP", "DOWN"):
            raise ValueError("first_side must be UP or DOWN")

        trade = PaperTrade(
            trade_id=trade_id,
            market_id=market_id,
            market_duration=market_duration,
            strategy=strategy,
            opened_at_ms=int(now_ms),
            hedge_eligible_at_ms=int(now_ms) + self.hedge_min_delay_ms,
            hedge_deadline_ms=int(now_ms) + self.hedge_max_delay_ms,
            first_side=first_side,
        )
        self.trades[trade_id] = trade

        fill = self.executor.simulate_buy(
            trade_id=trade_id, leg=1, side=first_side, ask=ask, ask_qty=ask_qty,
            requested_qty=requested_qty, timestamp_ms=now_ms
        )
        if fill is None:
            trade.status = "NO_FILL"
        else:
            self.executor.apply_fill(trade, fill)
            trade.status = "WAITING_HEDGE"

        await self._persist_temporal_trade(trade, now_ms)
        return trade

    async def try_temporal_hedge(
        self, *, trade_id, now_ms, opposite_ask, opposite_ask_qty
    ):
        """Attempt LEG 2 only inside the historical C3 15–30 second window."""
        trade = self.trades.get(trade_id)
        if trade is None:
            raise KeyError(trade_id)
        if trade.status != "WAITING_HEDGE":
            return trade

        if now_ms < trade.hedge_eligible_at_ms:
            return trade

        if now_ms >= trade.hedge_deadline_ms:
            trade.status = "FAILED_HEDGE"
            trade.closed_at_ms = int(now_ms)
            await self._persist_temporal_trade(trade, now_ms)
            return trade

        first_qty = trade.up_qty if trade.first_side == "UP" else trade.down_qty
        opposite = "DOWN" if trade.first_side == "UP" else "UP"

        fill = self.executor.simulate_buy(
            trade_id=trade_id, leg=2, side=opposite,
            ask=opposite_ask, ask_qty=opposite_ask_qty,
            requested_qty=first_qty, timestamp_ms=now_ms
        )
        if fill is not None:
            self.executor.apply_fill(trade, fill)

        if trade.unhedged_qty <= 1e-9 and trade.paired_qty > 0:
            trade.status = "FULLY_HEDGED"
            trade.closed_at_ms = int(now_ms)
        elif trade.paired_qty > 0:
            trade.status = "PARTIAL_HEDGE"
        else:
            trade.status = "WAITING_HEDGE"

        await self._persist_temporal_trade(trade, now_ms)
        return trade

    async def expire_temporal_trades(self, now_ms: int):
        """Mark overdue C3 hedges as failed; never fabricate a second-leg fill."""
        expired = []
        for trade in self.trades.values():
            if (
                trade.status in ("WAITING_HEDGE", "PARTIAL_HEDGE")
                and trade.hedge_deadline_ms is not None
                and now_ms >= trade.hedge_deadline_ms
            ):
                trade.status = "FAILED_HEDGE"
                trade.closed_at_ms = int(now_ms)
                await self._persist_temporal_trade(trade, now_ms)
                expired.append(trade.trade_id)
        return expired

    async def _persist_temporal_trade(self, trade, now_ms):
        async with aiosqlite.connect(self.path) as db:
            for fill in trade.fills:
                exists = await (
                    await db.execute(
                        "SELECT 1 FROM paper_fills WHERE session_id=? AND trade_id=? AND leg=? LIMIT 1",
                        (self.session_id, fill.trade_id, fill.leg),
                    )
                ).fetchone()
                if exists:
                    continue
                await db.execute(
                    """INSERT INTO paper_fills(
                    session_id,trade_id,timestamp_ms,leg,side,requested_qty,filled_qty,
                    observed_ask,fill_price,notional,fee,slippage_per_contract,slippage_cost,partial
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (self.session_id,fill.trade_id,fill.timestamp_ms,fill.leg,fill.side,
                     fill.requested_qty,fill.filled_qty,fill.observed_ask,fill.price,
                     fill.notional,fill.fee,fill.slippage_per_contract,fill.slippage_cost,
                     int(fill.partial))
                )

            await db.execute(
                """INSERT INTO paper_trades(
                session_id,trade_id,market_id,market_duration,strategy,opened_at_ms,
                closed_at_ms,status,hedge_status,up_qty,down_qty,paired_qty,unhedged_qty,
                up_cost,down_cost,fees,slippage_cost,gross_pnl,net_pnl,
                hedge_eligible_at_ms,hedge_deadline_ms,first_side
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id,trade_id) DO UPDATE SET
                closed_at_ms=excluded.closed_at_ms,status=excluded.status,
                hedge_status=excluded.hedge_status,up_qty=excluded.up_qty,
                down_qty=excluded.down_qty,paired_qty=excluded.paired_qty,
                unhedged_qty=excluded.unhedged_qty,up_cost=excluded.up_cost,
                down_cost=excluded.down_cost,fees=excluded.fees,
                slippage_cost=excluded.slippage_cost,gross_pnl=excluded.gross_pnl,
                net_pnl=excluded.net_pnl""",
                (self.session_id,trade.trade_id,trade.market_id,trade.market_duration,
                 trade.strategy,trade.opened_at_ms,trade.closed_at_ms,trade.status,
                 trade.hedge_status,trade.up_qty,trade.down_qty,trade.paired_qty,
                 trade.unhedged_qty,trade.up_cost,trade.down_cost,trade.fees,
                 trade.slippage_cost,trade.gross_pnl_if_settled,trade.net_pnl_if_settled,
                 trade.hedge_eligible_at_ms,trade.hedge_deadline_ms,trade.first_side)
            )
            await self._record_equity(db, now_ms)
            await db.commit()
