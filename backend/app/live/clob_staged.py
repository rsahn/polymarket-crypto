"""Staged authenticated CLOB boundary for D6.

This module deliberately cannot submit orders. It prepares a live-shaped request
using the installed SDK and returns an audit record. Real submission belongs in
a later, explicitly armed adapter after this staging path is validated.
"""
from __future__ import annotations

import inspect
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
        if n <= 0 or ask <= 0 or ask >= 1 or tick <= 0:
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
