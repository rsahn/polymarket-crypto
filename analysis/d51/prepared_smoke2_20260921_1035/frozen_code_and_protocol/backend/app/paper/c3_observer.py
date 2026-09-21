from __future__ import annotations

import sqlite3
from collections import deque
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from app.d5.identity import MarketIdentity


@dataclass(frozen=True)
class C3Anchor:
    ts_ms: int
    market_key: str
    market_slug: str
    condition_id: str
    token_up: str
    token_down: str
    expiry_ts_ms: int
    event_ts_ms: Optional[int]
    received_ts_ms: int
    market_duration: str
    anchor_group: int
    first_side: str
    btc_price: Optional[float]
    btc_return_1s: Optional[float]
    btc_return_5s: Optional[float]
    btc_return_15s: Optional[float]
    time_remaining_ms: Optional[int]
    first_bid: float
    first_ask: float
    first_bid_qty: float
    first_ask_qty: float
    first_spread: float
    opposite_bid: float
    opposite_ask: float
    opposite_bid_qty: float
    opposite_ask_qty: float
    opposite_spread: float
    depth_imbalance: Optional[float]


SCHEMA = """
CREATE TABLE IF NOT EXISTS c3_shadow_observations_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_ts_ms INTEGER NOT NULL,
    hedge_ts_ms INTEGER NOT NULL,
    delay_ms INTEGER NOT NULL,
    market_key TEXT NOT NULL,
    market_slug TEXT,
    condition_id TEXT,
    market_duration TEXT NOT NULL,
    anchor_group INTEGER NOT NULL,
    direction TEXT NOT NULL,

    btc_price REAL,
    btc_return_1s REAL,
    btc_return_5s REAL,
    btc_return_15s REAL,
    time_remaining_ms INTEGER,

    first_bid REAL NOT NULL,
    first_ask REAL NOT NULL,
    first_bid_qty REAL NOT NULL,
    first_ask_qty REAL NOT NULL,
    first_spread REAL NOT NULL,

    opposite_bid REAL NOT NULL,
    opposite_ask REAL NOT NULL,
    opposite_bid_qty REAL NOT NULL,
    opposite_ask_qty REAL NOT NULL,
    opposite_spread REAL NOT NULL,
    depth_imbalance REAL,

    second_ask REAL NOT NULL,
    second_ask_qty REAL NOT NULL,
    executable_qty REAL NOT NULL,
    pair_cost REAL NOT NULL,
    gross_edge REAL NOT NULL,
    net_edge_0 REAL NOT NULL,
    net_edge_0025 REAL NOT NULL,
    net_edge_005 REAL NOT NULL,
    net_edge_01 REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_c3_v2_unique
ON c3_shadow_observations_v2(anchor_ts_ms, market_key, direction);
CREATE INDEX IF NOT EXISTS idx_c3_v2_market_ts
ON c3_shadow_observations_v2(market_key, anchor_ts_ms);
CREATE INDEX IF NOT EXISTS idx_c3_v2_group
ON c3_shadow_observations_v2(market_key, anchor_group, direction);
"""


class C3ShadowObserver:
    """Prospective C3 observer V2. Observation only: never sends an order."""

    def __init__(
        self,
        db_path: Path,
        min_delay_ms: int = 15_000,
        max_delay_ms: int = 30_000,
        anchor_interval_ms: int = 1_000,
        group_interval_ms: int = 15_000,
    ):
        self.db_path = Path(db_path)
        if self.db_path.name == 'c3_shadow_live.db':
            raise RuntimeError('C3 dataset is audit-only. Start app.d5.live for prospective collection.')
        self.min_delay_ms = int(min_delay_ms)
        self.max_delay_ms = int(max_delay_ms)
        self.anchor_interval_ms = int(anchor_interval_ms)
        self.group_interval_ms = int(group_interval_ms)

        self.anchors: dict[tuple[str, str], deque[C3Anchor]] = {}
        self.active = {}
        self.retired = set()
        self.rejections = []
        self.last_anchor_ms: dict[tuple[str, str], int] = {}
        self.seen: set[tuple[int, str, str]] = set()
        self.btc_history: deque[tuple[int, float]] = deque()
        self.observations = 0

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as db, db:
            # Existing V2 databases need the two columns before an index can use them.
            columns = {
                row[1]
                for row in db.execute(
                    "PRAGMA table_info(c3_shadow_observations_v2)"
                )
            }

            if columns:
                if "market_slug" not in columns:
                    db.execute(
                        "ALTER TABLE c3_shadow_observations_v2 "
                        "ADD COLUMN market_slug TEXT"
                    )
                if "condition_id" not in columns:
                    db.execute(
                        "ALTER TABLE c3_shadow_observations_v2 "
                        "ADD COLUMN condition_id TEXT"
                    )
                db.commit()

            db.executescript(SCHEMA)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_c3_v2_slug "
                "ON c3_shadow_observations_v2(market_slug, anchor_ts_ms)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_c3_v2_condition "
                "ON c3_shadow_observations_v2(condition_id, anchor_ts_ms)"
            )
            db.commit()

    @staticmethod
    def _number(value) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _valid_quote(cls, side: dict) -> bool:
        bid = cls._number(side.get("bid"))
        ask = cls._number(side.get("ask"))
        bid_qty = cls._number(side.get("bid_qty")) or 0.0
        ask_qty = cls._number(side.get("ask_qty")) or 0.0
        return (
            bid is not None and ask is not None
            and 0.0 <= bid < ask <= 1.0
            and bid_qty > 0.0 and ask_qty > 0.0
        )

    def _update_btc(self, now_ms: int, btc_price: Optional[float]) -> None:
        if btc_price is None:
            return
        try:
            price = float(btc_price)
        except (TypeError, ValueError):
            return
        if not self.btc_history or now_ms > self.btc_history[-1][0]:
            self.btc_history.append((now_ms, price))
        cutoff = now_ms - 20_000
        while self.btc_history and self.btc_history[0][0] < cutoff:
            self.btc_history.popleft()

    def _btc_return(self, now_ms: int, current: Optional[float], lookback_ms: int) -> Optional[float]:
        if current is None or not self.btc_history:
            return None
        target = now_ms - lookback_ms
        candidates = [(ts, px) for ts, px in self.btc_history if ts <= target]
        if not candidates:
            return None
        _, old = candidates[-1]
        if old <= 0:
            return None
        return float(current / old - 1.0)

    @staticmethod
    def _duration(snapshot: dict) -> str:
        value = str(snapshot.get("market_key") or "unknown").lower()
        if "15m" in value:
            return "15m"
        if "5m" in value:
            return "5m"
        return value

    @staticmethod
    def _imbalance(first: dict, opposite: dict) -> Optional[float]:
        # Ask-depth imbalance from the perspective of LEG1.
        fq = float(first.get("ask_qty") or 0.0)
        oq = float(opposite.get("ask_qty") or 0.0)
        denom = fq + oq
        return (fq - oq) / denom if denom > 0 else None

    def _add_anchor(
        self,
        *,
        snapshot: dict,
        now_ms: int,
        market_key: str,
        first_side: str,
        first: dict,
        opposite: dict,
        btc_price: Optional[float],
    ) -> None:
        identity = MarketIdentity(snapshot['market_duration'], snapshot['market_slug'],
                                  snapshot['condition_id'], snapshot['token_up'],
                                  snapshot['token_down'], snapshot['expiry_ts_ms'])
        assert identity.matches(snapshot)
        assert now_ms < identity.expiry_ts_ms
        key = (identity.key, first_side)
        previous = self.last_anchor_ms.get(key)
        if previous is not None and now_ms - previous < self.anchor_interval_ms:
            return
        self.last_anchor_ms[key] = now_ms

        first_bid = float(first["bid"])
        first_ask = float(first["ask"])
        opposite_bid = float(opposite["bid"])
        opposite_ask = float(opposite["ask"])
        remaining = snapshot.get("time_remaining_ms")
        try:
            remaining = int(remaining) if remaining is not None else None
        except (TypeError, ValueError):
            remaining = None

        current_btc = float(btc_price) if btc_price is not None else None
        anchor = C3Anchor(
            ts_ms=now_ms,
            market_key=market_key,
            market_slug=str(snapshot.get("market_slug") or market_key),
            condition_id=str(
                snapshot.get("condition_id")
                or snapshot.get("market_slug")
                or market_key
            ),
            token_up=identity.token_up, token_down=identity.token_down,
            expiry_ts_ms=identity.expiry_ts_ms,
            event_ts_ms=snapshot.get('event_ts_ms'),
            received_ts_ms=int(snapshot['received_ts_ms']),
            market_duration=self._duration(snapshot),
            anchor_group=now_ms // self.group_interval_ms,
            first_side=first_side,
            btc_price=current_btc,
            btc_return_1s=self._btc_return(now_ms, current_btc, 1_000),
            btc_return_5s=self._btc_return(now_ms, current_btc, 5_000),
            btc_return_15s=self._btc_return(now_ms, current_btc, 15_000),
            time_remaining_ms=remaining,
            first_bid=first_bid,
            first_ask=first_ask,
            first_bid_qty=float(first.get("bid_qty") or 0.0),
            first_ask_qty=float(first.get("ask_qty") or 0.0),
            first_spread=first_ask - first_bid,
            opposite_bid=opposite_bid,
            opposite_ask=opposite_ask,
            opposite_bid_qty=float(opposite.get("bid_qty") or 0.0),
            opposite_ask_qty=float(opposite.get("ask_qty") or 0.0),
            opposite_spread=opposite_ask - opposite_bid,
            depth_imbalance=self._imbalance(first, opposite),
        )
        self.anchors.setdefault(identity.key, deque()).append(anchor)

    def _persist(self, anchor: C3Anchor, now_ms: int, second: dict, snapshot: dict) -> None:
        identity = MarketIdentity(anchor.market_duration, anchor.market_slug, anchor.condition_id,
                                  anchor.token_up, anchor.token_down, anchor.expiry_ts_ms)
        token = anchor.token_down if anchor.first_side == 'UP' else anchor.token_up
        if not identity.matches(snapshot) or second.get('token_id') != token:
            self.rejections.append('CROSS_MARKET_REJECT')
            return
        if now_ms >= anchor.expiry_ts_ms or not self.min_delay_ms <= now_ms-anchor.ts_ms <= self.max_delay_ms:
            self.rejections.append('EXPIRED_OR_OUTSIDE_WINDOW')
            return
        assert snapshot['market_slug'] == anchor.market_slug
        assert snapshot['condition_id'] == anchor.condition_id
        direction = f"{anchor.first_side}->{('DOWN' if anchor.first_side == 'UP' else 'UP')}"
        unique = (anchor.ts_ms, identity.key, direction)
        if unique in self.seen:
            return

        second_ask = float(second["ask"])
        second_qty = float(second.get("ask_qty") or 0.0)
        executable_qty = min(anchor.first_ask_qty, second_qty)
        if executable_qty <= 0:
            return

        pair_cost = anchor.first_ask + second_ask
        gross_edge = 1.0 - pair_cost
        delay_ms = now_ms - anchor.ts_ms

        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute(
                """INSERT OR IGNORE INTO c3_shadow_observations_v2(
                    anchor_ts_ms,hedge_ts_ms,delay_ms,market_key,market_slug,condition_id,market_duration,
                    anchor_group,direction,btc_price,btc_return_1s,btc_return_5s,
                    btc_return_15s,time_remaining_ms,first_bid,first_ask,
                    first_bid_qty,first_ask_qty,first_spread,opposite_bid,opposite_ask,
                    opposite_bid_qty,opposite_ask_qty,opposite_spread,depth_imbalance,
                    second_ask,second_ask_qty,executable_qty,pair_cost,gross_edge,
                    net_edge_0,net_edge_0025,net_edge_005,net_edge_01
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    anchor.ts_ms, now_ms, delay_ms, anchor.market_key,
                    anchor.market_slug, anchor.condition_id,
                    anchor.market_duration, anchor.anchor_group, direction,
                    anchor.btc_price, anchor.btc_return_1s, anchor.btc_return_5s,
                    anchor.btc_return_15s, anchor.time_remaining_ms,
                    anchor.first_bid, anchor.first_ask, anchor.first_bid_qty,
                    anchor.first_ask_qty, anchor.first_spread,
                    anchor.opposite_bid, anchor.opposite_ask,
                    anchor.opposite_bid_qty, anchor.opposite_ask_qty,
                    anchor.opposite_spread, anchor.depth_imbalance,
                    second_ask, second_qty, executable_qty, pair_cost, gross_edge,
                    gross_edge, gross_edge - 0.0025, gross_edge - 0.005,
                    gross_edge - 0.01,
                ),
            )
            if db.total_changes:
                self.seen.add(unique)
                self.observations += 1
                if self.observations <= 10 or self.observations % 100 == 0:
                    print(
                        f"C3_V2.1 #{self.observations}: {anchor.market_duration} {direction} "
                        f"slug={anchor.market_slug} group={anchor.anchor_group} "
                        f"delay={delay_ms}ms "
                        f"pair_cost={pair_cost:.4f} net@0.5%={gross_edge - 0.005:.4f} "
                        f"btc5s={anchor.btc_return_5s}"
                    )

    def observe(self, snapshot: dict, btc_price: Optional[float], now_ms: int) -> None:
        """Consume one already validated live snapshot. Never sends an order."""
        try:
            identity = MarketIdentity(snapshot['market_duration'], snapshot['market_slug'],
                                      snapshot['condition_id'], snapshot['token_up'],
                                      snapshot['token_down'], snapshot['expiry_ts_ms'])
        except (KeyError, ValueError):
            self.rejections.append('CROSS_MARKET_REJECT')
            return
        if not identity.matches(snapshot) or identity.key in self.retired:
            self.rejections.append('CROSS_MARKET_REJECT')
            return
        if now_ms >= identity.expiry_ts_ms:
            self.invalidate_market(identity.key)
            self.rejections.append('POST_EXPIRY_REJECT')
            return
        previous = self.active.get(identity.market_duration)
        if previous and previous != identity:
            self.invalidate_market(previous.key)
            if previous.key == identity.key:
                self.rejections.append('CROSS_MARKET_REJECT')
                return
        self.active[identity.market_duration] = identity
        self._update_btc(now_ms, btc_price)

        market_key = str(snapshot.get("market_key") or "unknown")
        up = snapshot.get("up") or {}
        down = snapshot.get("down") or {}
        if not (self._valid_quote(up) and self._valid_quote(down)):
            return

        q = self.anchors.setdefault(identity.key, deque())

        # Match old anchors first: current snapshot cannot be both LEG1 and LEG2.
        for anchor in list(q):
            age = now_ms - anchor.ts_ms
            if age < self.min_delay_ms or age > self.max_delay_ms:
                continue
            second = down if anchor.first_side == "UP" else up
            self._persist(anchor, now_ms, second, snapshot)

        while q and now_ms - q[0].ts_ms > self.max_delay_ms:
            q.popleft()

        self._add_anchor(
            snapshot=snapshot, now_ms=now_ms, market_key=market_key,
            first_side="UP", first=up, opposite=down, btc_price=btc_price,
        )
        self._add_anchor(
            snapshot=snapshot, now_ms=now_ms, market_key=market_key,
            first_side="DOWN", first=down, opposite=up, btc_price=btc_price,
        )

    def invalidate_market(self, identity_key):
        self.anchors.pop(identity_key, None)
        self.retired.add(identity_key)
        for key in list(self.last_anchor_ms):
            if key[0] == identity_key:
                del self.last_anchor_ms[key]
