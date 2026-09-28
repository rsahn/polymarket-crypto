"""Live CLOB transport using the installed polymarket SDK.

Submission is possible only when the external LiveArmGate is satisfied.
This module does not enable or arm live mode by itself.
"""
from __future__ import annotations
import asyncio,time
from dataclasses import asdict,is_dataclass

def _plain(x):
    if is_dataclass(x): return asdict(x)
    if hasattr(x,"model_dump"): return x.model_dump()
    if hasattr(x,"dict"): return x.dict()
    if hasattr(x,"__dict__"): return {k:v for k,v in vars(x).items() if not k.startswith("_")}
    return {"value":str(x)}

class LiveClobTransport:
    def __init__(self, client):
        self.client=client

    async def submit_limit(self, *, order):
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
        resp=await self.client.cancel_order(order_id=str(order_id))
        return {"ts_ms":int(time.time()*1000),"kind":"ORDER_CANCEL","response":_plain(resp)}

    async def submit_exit_limit(self, *, token_id, price, size):
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
    data=(event or {}).get("response") or {}
    if not isinstance(data,dict):return {"known":False,"raw":data}
    status=str(data.get("status") or data.get("state") or "").upper()
    original=float(data.get("original_size") or data.get("size") or 0)
    matched=float(data.get("size_matched") or data.get("matched_size") or data.get("filled_size") or 0)
    remaining=max(0.0,original-matched) if original else None
    return {"known":bool(status),"status":status,"original_size":original,
            "filled_size":matched,"remaining_size":remaining,"raw":data}
