"""Offline observation adapter; no feed, scheduler, strategy or monetary SDK imports.

No real V1 binding is supplied: its current callbacks omit entry events on exit
failure. Only complete explicit observations can be accounted for by this engine.
"""
from __future__ import annotations
import copy
import json
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_DOWN
from urllib.parse import urlparse
from .core import Ledger, BookTape, dec, digest, encode, safety

ROUNDINGS={"ROUND_HALF_EVEN_5DP":ROUND_HALF_EVEN,
           "ROUND_HALF_UP_5DP":ROUND_HALF_UP,"ROUND_DOWN_5DP":ROUND_DOWN}
# No reviewed exact exchange rounding/aggregation implementation has been found.
# Populating this registry requires separately reviewed normative evidence.
REVIEWED_ROUNDING_EVIDENCE = {}

@dataclass(frozen=True)
class FeeQualification:
    market_id:str
    token_id:str
    fee_enabled:bool|None
    fee_rate:str|None
    fee_source:str
    fee_schedule_version:str
    rounding_rule:str
    qualification_status:str
    evidence_hash:str
    reasons:tuple
    @classmethod
    def from_evidence(cls,market,token,*,source,version,rounding="UNKNOWN",
                      rounding_evidence="",synthetic=False):
        reasons=[]
        m=json.loads(encode(market))
        if not isinstance(m,dict): m={}
        schedule=m.get("feeSchedule") or {}
        if not isinstance(schedule,dict): schedule={}
        tokens=m.get("clobTokenIds",[])
        if isinstance(tokens,str):
            try:tokens=json.loads(tokens)
            except ValueError:tokens=[]
        if not isinstance(tokens,list): tokens=[]
        enabled=m.get("feesEnabled")
        if not m.get("id") or token not in tokens: reasons.append("MARKET_TOKEN_NOT_BOUND")
        if type(enabled)!=bool: reasons.append("FEE_ENABLEMENT_UNKNOWN")
        if urlparse(source).scheme!="https" or urlparse(source).hostname!="gamma-api.polymarket.com" or not version:
            reasons.append("FEE_SOURCE_OR_VERSION_UNKNOWN")
        rate=None
        try:
            rate=str(dec(schedule["rate"]))
            if not 0<=dec(rate)<=1 or schedule.get("exponent")!=1 or schedule.get("takerOnly") is not True:
                reasons.append("UNSUPPORTED_FEE_SCHEDULE")
            if enabled is False and dec(rate)!=0: reasons.append("CONTRADICTORY_DISABLED_RATE")
        except (KeyError,ValueError,ArithmeticError): reasons.append("FEE_RATE_UNKNOWN")
        reviewed=REVIEWED_ROUNDING_EVIDENCE.get(rounding_evidence)==rounding
        fixture=synthetic and rounding_evidence=="SYNTHETIC_FIXTURE_ONLY"
        if rounding not in ROUNDINGS or not (reviewed or fixture):
            reasons.append("ROUNDING_AND_AGGREGATION_UNPROVEN")
        status="MARKET_FEE_UNQUALIFIED" if reasons else ("SYNTHETIC_ONLY" if synthetic else "QUALIFIED")
        return cls(str(m.get("id","")),str(token),enabled,rate,source,version,rounding,status,
                   digest({"market":m,"source":source,"version":version,"rounding_evidence":rounding_evidence}),tuple(reasons))
    def fee(self,qty,price):
        if self.qualification_status not in ("QUALIFIED","SYNTHETIC_ONLY"):
            raise ValueError("MARKET_FEE_UNQUALIFIED")
        q,p=dec(qty),dec(price)
        if q<0 or not 0<p<1: raise ValueError("INVALID_FEE_INPUT")
        # Synthetic exact rounding is explicit; never a normative default.
        return (q*dec(self.fee_rate)*p*(1-p)).quantize(Decimal(".00001"),rounding=ROUNDINGS[self.rounding_rule])
    def record(self): return asdict(self)

class ProspectiveEventAdapter:
    def __init__(self,journal,fees,*,synthetic=False):
        safety(); self.journal=journal; self.fees=dict(fees); self.synthetic=synthetic
        self.ledger=Ledger(next(iter(fees.values())) if fees else None)
        self.tape=BookTape(); self.states={}; self.marks={}; self.accounting=[]
        self.ended=False; self.fee_annotations=set()
        for row in journal.records: self._apply(row)
    def _policy(self,e):
        f=self.fees.get((e["market_id"],e["token_id"]))
        allowed=("QUALIFIED","SYNTHETIC_ONLY") if self.synthetic else ("QUALIFIED",)
        if f is None or f.qualification_status not in allowed or f.market_id!=e["market_id"] or f.token_id!=e["token_id"]: raise ValueError("MARKET_FEE_UNQUALIFIED")
        return f
    def _apply(self,e):
        if self.ended: raise ValueError("SESSION_ENDED")
        kind=e["kind"]; token=e["token_id"]; trade=e.get("trade_id")
        prior=self.ledger.realized; fees_before=self.ledger.fees
        if kind not in ("SESSION_END","MARK"):
            self.ledger.policy=self._policy(e)
        if kind=="SIGNAL":
            if not trade or trade in self.states: raise ValueError("CALLBACK_ORDER")
            self.states[trade]={"stage":"SIGNAL","token":token,"market":e["market_id"],"qty":Decimal(0)}
        elif kind not in ("SESSION_END","MARK"):
            state=self.states.get(trade)
            if not state or state["token"]!=token or state["market"]!=e["market_id"]:
                raise ValueError("CALLBACK_ORDER_OR_IDENTITY")
            stage=state["stage"]
            if kind=="ENTRY_INTENT":
                if stage!="SIGNAL" or dec(e["notional"])!=25: raise ValueError("CALLBACK_ORDER_OR_FIXED25")
                state["stage"]="ENTRY"
            elif kind=="CASH_RESERVED":
                if stage!="ENTRY": raise ValueError("CALLBACK_ORDER")
                self.ledger.reserve(trade,e["notional"])
            elif kind=="CASH_RELEASED": self.ledger.release(trade)
            elif kind in ("ENTRY_BOOK","EXIT_BOOK"):
                if stage!=("ENTRY" if kind=="ENTRY_BOOK" else "EXIT"): raise ValueError("CALLBACK_ORDER")
                if e["book_ts"] is None: raise ValueError("BOOK_TIME_MISSING")
                self.tape.observe(e["event_id"],token,e["source_ts"],e["recv_ts"],
                                  e["decision_ts"],e["asks"],e["bids"])
            elif kind in ("ENTRY_FILL","ENTRY_PARTIAL_FILL","EXIT_FILL","EXIT_PARTIAL_FILL"):
                buy=kind.startswith("ENTRY")
                if stage!=("ENTRY" if buy else "EXIT"): raise ValueError("CALLBACK_ORDER")
                q,p=dec(e["qty"]),dec(e["price"])
                if dec(e["notional"])!=q*p or dec(e["fee"])!=self.ledger.policy.fee(q,p):
                    raise ValueError("OBSERVED_FEE_OR_NOTIONAL_MISMATCH")
                # Validate the observed price/quantity; never decide/reprice a V1 fill.
                if not buy and q>state["qty"]: raise ValueError("TRADE_POSITION_OVERSELL")
                side="BUY" if buy else "SELL"
                book=self.tape.at(token,e["decision_ts"])
                if not book: raise ValueError("BOOK_MISSING")
                visible,remaining=self.tape.depth.get((token,side),{}).get(p,(0,0))
                if q<=0 or remaining<q: raise ValueError("OBSERVED_FILL_EXCEEDS_PERSISTENT_LIQUIDITY")
                self.tape.depth[token,side][p]=(visible,remaining-q)
                if buy: self.ledger.buy(e["event_id"],trade,token,q,p,e["event_ts"])
                else: self.ledger.sell(e["event_id"],token,q,p,e["event_ts"])
                state["qty"]+=q if buy else -q
                self.marks.pop(token,None)
            elif kind=="ENTRY_NO_FILL":
                if stage!="ENTRY" or state["qty"]!=0: raise ValueError("CALLBACK_ORDER")
                state["stage"]="NO_ENTRY"
            elif kind=="EXIT_INTENT":
                if stage!="ENTRY" or state["qty"]<=0:
                    raise ValueError("CALLBACK_ORDER")
                state["stage"]="EXIT"
            elif kind=="EXIT_NO_FILL":
                if stage!="EXIT": raise ValueError("CALLBACK_ORDER")
                self.marks.pop(token,None)
            elif kind in ("POSITION_OPEN","POSITION_RESIDUAL"):
                if dec(e["qty"])!=self.ledger.positions.get(token,{}).get("qty",0):
                    raise ValueError("POSITION_MISMATCH")
            elif kind=="POSITION_SETTLED":
                self.ledger.settle(e["event_id"],token,e["payout"],e["event_ts"],e["available_ts"],e["source"])
                for st in self.states.values():
                    if st["token"]==token: st["qty"]=Decimal(0)
            elif kind=="FEE":
                referenced=next((x for x in self.ledger.events if x["id"]==e.get("fill_event_id")),None)
                if e.get("fill_event_id") in self.fee_annotations or not referenced or dec(e["fee"])!=referenced.get("fee"): raise ValueError("FEE_REFERENCE_MISMATCH")
                self.fee_annotations.add(e["fill_event_id"])
                # Annotation only: the fee was expensed exactly once on the fill.
        if kind=="MARK":
            self.marks=dict(e["net_unit_marks"]); self.ledger.mark(self.marks)
        if kind=="SESSION_END": self.ended=True
        m=self.ledger.mark(self.marks)
        self.accounting.append({"event_id":e["event_id"],"event_ts":e["event_ts"],
            "market_id":e["market_id"],"direction":e["direction"],
            "trade_closed":bool(trade in self.states and self.states[trade]["qty"]==0 and kind in ("EXIT_FILL","EXIT_PARTIAL_FILL","POSITION_SETTLED")),
            "kind":kind,"net_delta":self.ledger.realized-prior,
            "fee_delta":self.ledger.fees-fees_before,"equity":m["equity"],
            "open_qty":sum((p["qty"] for p in self.ledger.positions.values()),Decimal(0))})
    def observe(self,event):
        safety()
        # Transactional simulation on detached state before append. Accepted state
        # becomes visible only after durable append; failed validation writes nothing.
        row=self.journal.preview(event)
        trial=object.__new__(type(self))
        for name,value in self.__dict__.items():
            setattr(trial,name,value if name=="journal" else copy.deepcopy(value))
        trial._apply(row)
        self.journal.append(event)
        for name,value in trial.__dict__.items():
            if name!="journal": setattr(self,name,value)
        return row["event_hash"]
