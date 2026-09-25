"""Live CLOB transport using the installed polymarket SDK.

Submission is possible only when the external LiveArmGate is satisfied.
This module does not enable or arm live mode by itself.
"""
from __future__ import annotations
import asyncio,time,math
from dataclasses import asdict,is_dataclass

def _plain(x):
    if isinstance(x, dict): return dict(x)
    if is_dataclass(x): return asdict(x)
    if hasattr(x,"model_dump"): return x.model_dump()
    if hasattr(x,"dict"): return x.dict()
    if hasattr(x,"__dict__"): return {k:v for k,v in vars(x).items() if not k.startswith("_")}
    return {"value":str(x)}

class LiveClobTransport:
    def __init__(self, client):
        self.client=client

    async def submit_limit(self, *, order):
        raise RuntimeError("USER_APPROVAL_REQUIRED")
        resp=await self.client.place_limit_order(
            token_id=str(order.token_id),
            price=order.limit_price,
            size=order.size,
            side="BUY",
            post_only=False,
        )
        data=_plain(resp)
        return {"ts_ms":int(time.time()*1000),"kind":"ENTRY_SUBMIT","response":data}

    async def get_order(self, *, order_id):
        resp=await self.client.get_order(order_id=str(order_id))
        return {"ts_ms":int(time.time()*1000),"kind":"ORDER_STATUS","response":_plain(resp)}

    async def cancel_order(self, *, order_id):
        raise RuntimeError("USER_APPROVAL_REQUIRED")
        resp=await self.client.cancel_order(order_id=str(order_id))
        return {"ts_ms":int(time.time()*1000),"kind":"ORDER_CANCEL","response":_plain(resp)}

    async def submit_exit_limit(self, *, token_id, price, size):
        raise RuntimeError("USER_APPROVAL_REQUIRED")
        resp=await self.client.place_limit_order(
            token_id=str(token_id), price=price, size=size, side="SELL", post_only=False
        )
        return {"ts_ms":int(time.time()*1000),"kind":"EXIT_SUBMIT","response":_plain(resp)}


def extract_order_id(event):
    """Best-effort extraction from SDK AcceptedOrder payload; fail closed if absent."""
    data=(event or {}).get("response") or {}
    for key in ("order_id","orderID","id"):
        value=data.get(key) if isinstance(data,dict) else None
        if value:return str(value)
    return None

def normalize_order_status(event):
    """Reject unknown, incomplete, conflicting and non-finite remote reports."""
    data = event.get("response") if isinstance(event, dict) else None
    bad = {"known": False}
    if not isinstance(data, dict): return bad
    statuses = [str(data[k]).upper() for k in ("status", "state") if k in data]
    allowed = {"LIVE", "OPEN", "PENDING", "FILLED", "MATCHED", "CANCELLED", "CANCELED", "EXPIRED"}
    if not statuses or len(set(statuses)) != 1 or statuses[0] not in allowed: return bad
    def number(keys):
        values = [data[k] for k in keys if k in data]
        if not values or any(isinstance(v, bool) for v in values): raise ValueError()
        values = [float(v) for v in values]
        if any(not math.isfinite(v) for v in values) or len(set(values)) != 1: raise ValueError()
        return values[0]
    try:
        original = number(("original_size", "size"))
        filled = number(("size_matched", "matched_size", "filled_size"))
        if original <= 0 or filled < 0 or filled > original: return bad
        if statuses[0] in {"FILLED", "MATCHED"} and filled != original: return bad
    except (TypeError, ValueError, OverflowError): return bad
    return {"known": True, "status": statuses[0], "original_size": original,
            "filled_size": filled, "remaining_size": original-filled}
