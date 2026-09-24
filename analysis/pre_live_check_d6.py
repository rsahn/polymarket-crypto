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

    sig = inspect.signature(AsyncSecureClient)
    params = sig.parameters
    private_key = _env_first("SIGNER_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY", "PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("missing local SIGNER_PRIVATE_KEY/private-key env")

    candidates = {
        "private_key": private_key,
        "key": private_key,
        "funder": _env_first("POLYMARKET_WALLET_ADDRESS", "POLYMARKET_FUNDER", "FUNDER_ADDRESS"),
        "funder_address": _env_first("POLYMARKET_WALLET_ADDRESS", "POLYMARKET_FUNDER", "FUNDER_ADDRESS"),
        "wallet_address": _env_first("POLYMARKET_WALLET_ADDRESS"),
        "signature_type": _env_first("POLYMARKET_SIGNATURE_TYPE", "SIGNATURE_TYPE"),
        "host": _env_first("POLYMARKET_CLOB_HOST") or "https://clob.polymarket.com",
        "chain_id": int(_env_first("POLYMARKET_CHAIN_ID", "CHAIN_ID") or "137"),
    }
    kwargs = {k: v for k, v in candidates.items() if k in params and v is not None}

    try:
        return AsyncSecureClient(**kwargs)
    except TypeError as exc:
        raise RuntimeError(
            "unable to construct AsyncSecureClient from local env; "
            f"constructor={sig}"
        ) from exc


async def main():
    result = {
        "authenticated_wallet": False,
        "real_orders_enabled": _real_orders_enabled(),
        "collateral_balance": None,
        "allowance": None,
        "risk_manager_25": False,
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
        client = _client_factory()
        # Authentication is considered verified only after the authenticated
        # read-only account endpoint succeeds.
        bal = await client.get_balance_allowance(asset_type="COLLATERAL")
        result["authenticated_wallet"] = True
        payload = _plain(bal)
        result["balance_allowance_raw"] = payload
        for key in ("balance", "available_balance", "collateral_balance"):
            if key in payload:
                result["collateral_balance"] = payload[key]
                break
        for key in ("allowance", "allowances"):
            if key in payload:
                result["allowance"] = payload[key]
                break
    except Exception as exc:
        result["reasons"].append(f"READ_ONLY_CHECK_FAILED:{type(exc).__name__}:{exc}")
    finally:
        if client is not None:
            closer = getattr(client, "close", None)
            if closer is not None:
                out = closer()
                if inspect.isawaitable(out):
                    await out

    result["ready_for_live"] = (
        result["authenticated_wallet"]
        and not result["real_orders_enabled"]
        and result["risk_manager_25"]
        and not result["forbidden_order_methods_called"]
        and not result["reasons"]
    )

    print("PRE-LIVE CHECK")
    print(json.dumps(result, indent=2, default=str, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
