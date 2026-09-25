"""Explicit readers for future execution; no optimistic default risk state."""
from dataclasses import dataclass
from typing import Callable
from .execution import ExecutionController, ExecutionBlocked


@dataclass(frozen=True)
class ExecutionStateSources:
    book: Callable
    risk: Callable
    geo: Callable
    signal: Callable
    position: Callable

    def __call__(self):
        book,risk,geo,signal,position = (read() for read in (self.book,self.risk,self.geo,self.signal,self.position))
        if not all(isinstance(x,dict) for x in (book,risk,geo,signal,position)):
            raise ExecutionBlocked("SOURCE_UNAVAILABLE")
        return dict(connected=book.get("connected"),book_synced=book.get("book_synced"),
            market_slug=book.get("market_slug"),token_id=book.get("token_id"),book_ms=book.get("observed_ms"),
            expiry_ms=book.get("expiry_ms"),fillable_shares=book.get("fillable_shares"),
            risk_ms=risk.get("observed_ms"),session_pnl=risk.get("session_pnl"),available_usdc=risk.get("available_usdc"),
            geoblock_blocked=geo.get("blocked"),geo_ms=geo.get("observed_ms"),
            signal_valid=signal.get("valid"),signal_ms=signal.get("observed_ms"),
            open_positions=position.get("open_positions"),recovery_complete=position.get("recovery_complete"))


def staging_gate(reader,order,*,now_ms):
    if reader is None: return {"allow":False,"reasons":["EXECUTION_SOURCES_NOT_CONNECTED"]}
    try:
        controller=ExecutionController(None,None,None,reader,clock=lambda:now_ms)
        controller.gates(order)
    except (ExecutionBlocked,TypeError,ValueError,KeyError):
        return {"allow":False,"reasons":["EXECUTION_STATE_REJECTED"]}
    return {"allow":True,"reasons":[]}
