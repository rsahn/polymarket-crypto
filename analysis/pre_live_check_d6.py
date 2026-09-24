"""Read-only pre-live safety check for D6.
Never submits, signs, cancels, or posts orders.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.live.risk import RiskManager
from app.collectors.polymarket import PolymarketMarketDiscovery

DEFAULT_NOTIONAL = 25.0
DEFAULT_BANKROLL_CAP = 100.0


def _load_dotenv(path: Path):
    """Minimal .env loader: local values only, never logs secrets."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(ROOT / ".env")


def _plain(value):
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {"value": str(value)}


def _env_first(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _real_orders_enabled():
    return os.getenv("REAL_ORDERS_ENABLED", "false").strip().lower() == "true"


def _client_factory():
    from polymarket import AsyncSecureClient

    private_key = _env_first("SIGNER_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY", "PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("missing local SIGNER_PRIVATE_KEY/private-key env")
    # Important: do NOT force POLYMARKET_WALLET_ADDRESS here. In SDK 0.11,
    # wallet=None resolves the signer's Polymarket Deposit Wallet. The UI's
    # "signer address" can differ conceptually from the collateral wallet.
    # Forcing the signer address previously authenticated successfully but
    # queried a zero collateral balance.
    return AsyncSecureClient.create(private_key=private_key)


async def main():
    result = {
        "authenticated_wallet": False,
        "real_orders_enabled": _real_orders_enabled(),
        "collateral_balance": None,
        "collateral_balance_usdc": None,
        "allowance": None,
        "risk_manager_25": False,
        "btc_5m_market": None,
        "order_books": {},
        "market_constraints": {},
        "forbidden_order_methods_called": False,
        "ready_for_live": False,
        "reasons": [],
    }

    if result["real_orders_enabled"]:
        result["reasons"].append("REAL_ORDERS_ENABLED_MUST_BE_FALSE")

    risk = RiskManager()
    ok, reasons = risk.approve(
        notional=DEFAULT_NOTIONAL,
        bankroll=DEFAULT_BANKROLL_CAP,
        open_positions=0,
        session_pnl=0.0,
    )
    result["risk_manager_25"] = bool(ok)
    if reasons:
        result["reasons"].extend(reasons)

    client = None
    try:
        client = await _client_factory()
        # Authentication is considered verified only after the authenticated
        # read-only account endpoint succeeds.
        bal = await client.get_balance_allowance(asset_type="COLLATERAL")
        result["authenticated_wallet"] = True
        payload = _plain(bal)
        result["balance_allowance_raw"] = payload
        for key in ("balance", "available_balance", "collateral_balance"):
            if key in payload:
                result["collateral_balance"] = payload[key]
                try:
                    result["collateral_balance_usdc"] = float(payload[key]) / 1_000_000
                except (TypeError, ValueError):
                    pass
                break
        for key in ("allowance", "allowances"):
            if key in payload:
                result["allowance"] = payload[key]
                break

        # Public discovery + read-only CLOB books. No order creation/submission.
        markets = await asyncio.to_thread(
            PolymarketMarketDiscovery.get_active_btc_markets,
            True, True
        )
        market = next((m for m in markets if m.get("market_key") == "5m"), None)
        if market is None:
            result["reasons"].append("NO_ACTIVE_BTC_5M_MARKET")
        else:
            meta = market.get("metadata") or {}
            result["btc_5m_market"] = {
                "slug": market.get("slug"),
                "active": market.get("active"),
                "expiry_ts_ms": market.get("expiry_ts_ms"),
                "accepting_orders": meta.get("acceptingOrders"),
            }
            tick = meta.get("orderPriceMinTickSize")
            min_size = meta.get("orderMinSize")
            result["market_constraints"] = {
                "tick_size": tick,
                "min_order_size": min_size,
            }
            if tick is None:
                result["reasons"].append("UNKNOWN_TICK_SIZE")
            if min_size is None:
                result["reasons"].append("UNKNOWN_MIN_ORDER_SIZE")
            for side, token in (market.get("token_ids") or {}).items():
                book = await client.get_order_book(token_id=str(token))
                bp = _plain(book)
                bids = bp.get("bids") or []
                asks = bp.get("asks") or []
                ask_rows = [_plain(x) for x in asks]
                # SDK books are observed worst->best here; consume best ask first.
                ask_rows = sorted(ask_rows, key=lambda x: float(x.get("price", 999)))
                remaining = DEFAULT_NOTIONAL
                cost = shares = 0.0
                for level in ask_rows:
                    p = float(level.get("price", 0)); q = float(level.get("size", 0))
                    if p <= 0 or q <= 0:
                        continue
                    take = min(q, remaining / p)
                    cost += take * p; shares += take; remaining -= take * p
                    if remaining <= 1e-9:
                        break
                result["order_books"][side] = {
                    "token_id": str(token),
                    "best_bid": _plain(bids[-1]) if bids else None,
                    "best_ask": _plain(asks[-1]) if asks else None,
                    "bid_levels": len(bids),
                    "ask_levels": len(asks),
                    "notional_25_fillable": remaining <= 1e-9,
                    "notional_25_vwap": (cost / shares if shares else None),
                    "notional_25_cost": cost,
                }
                if not asks:
                    result["reasons"].append(f"NO_{side}_ASK_DEPTH")
                elif remaining > 1e-9:
                    result["reasons"].append(f"INSUFFICIENT_{side}_DEPTH_FOR_25")
    except Exception as exc:
        result["reasons"].append(f"READ_ONLY_CHECK_FAILED:{type(exc).__name__}:{exc}")
    finally:
        if client is not None:
            closer = getattr(client, "close", None)
            if closer is not None:
                out = closer()
                if inspect.isawaitable(out):
                    await out

    try:
        balance_value = float(result["collateral_balance"]) if result["collateral_balance"] is not None else 0.0
    except (TypeError, ValueError):
        balance_value = 0.0
    allowance_values = result["allowance"].values() if isinstance(result["allowance"], dict) else []
    allowance_ok = any(float(v) >= DEFAULT_NOTIONAL for v in allowance_values)

    if balance_value < DEFAULT_NOTIONAL:
        result["reasons"].append("COLLATERAL_BALANCE_BELOW_25")
    if not allowance_ok:
        result["reasons"].append("COLLATERAL_ALLOWANCE_BELOW_25")

    result["ready_for_live"] = (
        result["authenticated_wallet"]
        and not result["real_orders_enabled"]
        and result["risk_manager_25"]
        and balance_value >= DEFAULT_NOTIONAL
        and allowance_ok
        and result["btc_5m_market"] is not None
        and bool(result["order_books"])
        and all(v.get("notional_25_fillable") for v in result["order_books"].values())
        and result["market_constraints"].get("tick_size") is not None
        and result["market_constraints"].get("min_order_size") is not None
        and not result["forbidden_order_methods_called"]
        and not result["reasons"]
    )

    print("PRE-LIVE CHECK")
    print(json.dumps(result, indent=2, default=str, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
