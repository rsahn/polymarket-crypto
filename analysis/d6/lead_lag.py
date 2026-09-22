"""D6 offline BTC -> Polymarket lead/lag primitives.

Pure functions first: deterministic, testable, and deliberately disconnected
from order execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Tick:
    ts_ms: int
    value: float
    market_slug: str | None = None
    expiry_ts_ms: int | None = None


@dataclass(frozen=True)
class Response:
    anchor_ts_ms: int
    horizon_ms: int
    btc_return: float
    poly_change: float | None


def pct_move(a: float, b: float) -> float:
    if a <= 0:
        raise ValueError("anchor value must be positive")
    return (b / a) - 1.0


def value_at_or_after(series: Sequence[Tick], ts_ms: int) -> Tick | None:
    """First observation at/after ts_ms. Input must be timestamp-sorted."""
    if not series:
        return None
    times = [x.ts_ms for x in series]
    i = bisect_left(times, ts_ms)
    return series[i] if i < len(series) else None


def event_study(
    btc: Sequence[Tick],
    poly: Sequence[Tick],
    *,
    lookback_ms: int,
    threshold: float,
    horizons_ms: Iterable[int] = (50, 100, 250, 500, 1000),
    cooldown_ms: int = 0,
) -> list[Response]:
    """Create BTC-move anchors and measure subsequent Polymarket changes.

    This is intentionally a research primitive, not a trading strategy.
    """
    if lookback_ms <= 0 or threshold <= 0:
        raise ValueError("lookback_ms and threshold must be positive")
    if any(btc[i].ts_ms > btc[i + 1].ts_ms for i in range(len(btc) - 1)):
        raise ValueError("btc must be sorted")
    if any(poly[i].ts_ms > poly[i + 1].ts_ms for i in range(len(poly) - 1)):
        raise ValueError("poly must be sorted")

    if cooldown_ms < 0:
        raise ValueError("cooldown_ms must be non-negative")
    out: list[Response] = []
    last_anchor_ts = None
    for current in btc:
        prior = value_at_or_after(btc, current.ts_ms - lookback_ms)
        if prior is None or prior.ts_ms >= current.ts_ms:
            continue
        move = pct_move(prior.value, current.value)
        if abs(move) < threshold:
            continue
        if last_anchor_ts is not None and current.ts_ms - last_anchor_ts < cooldown_ms:
            continue
        p0 = value_at_or_after(poly, current.ts_ms)
        if p0 is None:
            continue
        last_anchor_ts = current.ts_ms
        for horizon in horizons_ms:
            if horizon <= 0:
                raise ValueError("horizons must be positive")
            ph = value_at_or_after(poly, current.ts_ms + horizon)
            comparable = (
                ph is not None
                and p0.market_slug == ph.market_slug
                and (p0.expiry_ts_ms is None or current.ts_ms + horizon < p0.expiry_ts_ms)
            )
            out.append(Response(
                anchor_ts_ms=current.ts_ms,
                horizon_ms=horizon,
                btc_return=move,
                poly_change=(ph.value - p0.value) if comparable else None,
            ))
    return out


def load_d5_timelines(db_path, *, market_duration: str, side: str = "UP"):
    """Load source/receive-timestamped BTC and executable Polymarket ask timelines."""
    import json
    import sqlite3
    import zlib

    if market_duration not in ("5m", "15m"):
        raise ValueError("market_duration must be 5m or 15m")
    side = side.upper()
    if side not in ("UP", "DOWN"):
        raise ValueError("side must be UP or DOWN")

    def unpack(value):
        if isinstance(value, bytes):
            value = zlib.decompress(value).decode("utf-8")
        return json.loads(value)

    db = sqlite3.connect(str(db_path))
    try:
        schema = db.execute("SELECT version FROM schema_info").fetchone()
        if schema != (2,):
            raise ValueError("D6 requires validated D5.1 schema v2")
        session = db.execute(
            "SELECT session_id,status FROM sessions ORDER BY started_at_ms DESC LIMIT 1"
        ).fetchone()
        if not session or session[1] != "STOPPED":
            raise ValueError("D6 requires a cleanly STOPPED D5.1 session")

        btc = []
        for event_ts, recv_ts, payload in db.execute(
            "SELECT event_ts_ms,received_ts_ms,payload_json FROM events "
            "WHERE session_id=? AND kind='BTC' ORDER BY received_ts_ms,event_id",
            (session[0],),
        ):
            obj = unpack(payload)
            price = obj.get("price")
            if price is not None:
                btc.append(Tick(int(recv_ts), float(price)))

        poly = [
            Tick(int(ts), float(ask), slug, int(expiry))
            for ts, ask, slug, expiry in db.execute(
                "SELECT bs.received_ts_ms,bs.best_ask,e.market_slug,m.expiry_ts_ms "
                "FROM events e JOIN book_sides bs ON bs.event_id=e.event_id "
                "JOIN markets m ON m.market_slug=e.market_slug "
                "WHERE e.session_id=? AND e.kind='BOOK' AND e.market_duration=? "
                "AND bs.side=? AND bs.best_ask IS NOT NULL "
                "ORDER BY bs.received_ts_ms,e.event_id",
                (session[0], market_duration, side),
            )
        ]
        return btc, poly
    finally:
        db.close()


def summarize(rows: Sequence[Response]) -> dict:
    """Deterministic per-horizon descriptive summary; no profitability claim."""
    grouped = {}
    for row in rows:
        grouped.setdefault(row.horizon_ms, []).append(row)
    out = {}
    for horizon, values in sorted(grouped.items()):
        usable = [r.poly_change for r in values if r.poly_change is not None]
        signed = [
            change if r.btc_return > 0 else -change
            for r, change in ((r, r.poly_change) for r in values)
            if change is not None
        ]
        up = [r for r in values if r.btc_return > 0]
        down = [r for r in values if r.btc_return < 0]
        out[str(horizon)] = {
            "anchors": len(values),
            "btc_up_anchors": len(up),
            "btc_down_anchors": len(down),
            "usable": len(usable),
            "mean_poly_change": None if not usable else sum(usable) / len(usable),
            "mean_directional_response": None if not signed else sum(signed) / len(signed),
            "same_direction_fraction": None if not signed else sum(x > 0 for x in signed) / len(signed),
        }
    return out
