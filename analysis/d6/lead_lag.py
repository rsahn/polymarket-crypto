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

    out: list[Response] = []
    for current in btc:
        prior = value_at_or_after(btc, current.ts_ms - lookback_ms)
        if prior is None or prior.ts_ms >= current.ts_ms:
            continue
        move = pct_move(prior.value, current.value)
        if abs(move) < threshold:
            continue
        p0 = value_at_or_after(poly, current.ts_ms)
        if p0 is None:
            continue
        for horizon in horizons_ms:
            if horizon <= 0:
                raise ValueError("horizons must be positive")
            ph = value_at_or_after(poly, current.ts_ms + horizon)
            out.append(Response(
                anchor_ts_ms=current.ts_ms,
                horizon_ms=horizon,
                btc_return=move,
                poly_change=None if ph is None else ph.value - p0.value,
            ))
    return out
