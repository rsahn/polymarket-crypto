"""Prospective validation primitives. Offline only; no transport or strategy imports.

Qualification remains BLOCKED until a reviewed collector/evaluator binds these
primitives to immutable observations and market-specific fee evidence.
"""
from __future__ import annotations
import hashlib, json, os, time
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

ZERO=Decimal(0)
def dec(x):
    v=Decimal(str(x))
    if not v.is_finite(): raise ValueError("NON_FINITE")
    return v
def encode(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False,
                      default=lambda v: str(v) if isinstance(v,Decimal) else (_ for _ in ()).throw(TypeError(type(v))))
def digest(x): return hashlib.sha256(encode(x).encode()).hexdigest()
def file_hash(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def write_once(path,payload):
    """Exclusive create and fsync; interrupted/torn files fail closed, never replaced."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8",newline="\n") as f:
        f.write(encode(payload)+"\n");f.flush();os.fsync(f.fileno())
def safety():
    for k in ("REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED"):
        if os.environ.get(k,"false").strip().lower()!="false": raise ValueError("LIVE_FORBIDDEN:"+k)
    return {"REAL_ORDERS_ENABLED":False,"LIVE_EXECUTION_ARMED":False,"submit_allowed":False}

@dataclass(frozen=True)
class FeePolicy:
    rate:str
    source:str
    version:str
    evidence_hash:str
    verified:bool=False
    def fee(self,qty,price):
        q,p,r=dec(qty),dec(price),dec(self.rate)
        if not self.verified or not all((self.source,self.version,self.evidence_hash)):
            raise ValueError("NET_EDGE_UNQUALIFIABLE")
        if q<0 or not 0<p<1 or not 0<=r<=1: raise ValueError("INVALID_FEE_INPUT")
        # Explicit conservative simulation bound, NOT asserted exchange tie rounding.
        return (q*r*p*(1-p)).quantize(Decimal(".00001"),rounding=ROUND_CEILING)

class Ledger:
    """Average-cost accounting, fees expensed at fill; marks are NET liquidation values.

    equity = cash + liquidation_value
           = initial + realized_net + (liquidation_value - remaining_cost_basis).
    Reservations are a subset of cash, never an additional asset.
    Unknown liquidation values propagate UNKNOWN instead of excluding positions.
    """
    def __init__(self,policy:FeePolicy,initial="500"):
        safety()
        self.policy=policy;self.initial=dec(initial)
        if self.initial<=0: raise ValueError("INVALID_INITIAL")
        self.cash=self.initial;self.reservations={};self.positions={}
        self.realized=ZERO;self.fees=ZERO;self.turnover=ZERO
        self.ids=set();self.last_ts=-1;self.events=[]
    @property
    def reserved(self): return sum(self.reservations.values(),ZERO)
    @property
    def available(self): return self.cash-self.reserved
    def reserve(self,order,amount):
        a=dec(amount)
        if order in self.reservations or a<=0 or a>self.available: raise ValueError("RESERVATION_REJECTED")
        self.reservations[order]=a
    def release(self,order):
        if order not in self.reservations: raise ValueError("UNKNOWN_RESERVATION")
        del self.reservations[order]
    def _check(self,event,ts):
        if not event or event in self.ids: raise ValueError("DUPLICATE_EVENT")
        if not isinstance(ts,int) or ts<self.last_ts: raise ValueError("OUT_OF_ORDER_EVENT")
    def _record(self,event,ts,kind,**fields):
        self.ids.add(event);self.last_ts=ts
        self.events.append({"id":event,"ts_ms":ts,"kind":kind,**fields})
        if self.available<0: raise AssertionError("NEGATIVE_AVAILABLE")
    def buy(self,event,order,token,qty,price,ts):
        self._check(event,ts);q,p=dec(qty),dec(price)
        if not token or q<=0 or not 0<p<1: raise ValueError("INVALID_FILL")
        fee=self.policy.fee(q,p);cost=q*p;debit=cost+fee
        if debit>self.reservations.get(order,ZERO): raise ValueError("INSUFFICIENT_RESERVATION")
        pos=self.positions.get(token,{"qty":ZERO,"cost":ZERO})
        self.cash-=debit;self.reservations[order]-=debit
        self.positions[token]={"qty":pos["qty"]+q,"cost":pos["cost"]+cost}
        self.realized-=fee;self.fees+=fee;self.turnover+=cost
        self._record(event,ts,"BUY",token=token,qty=q,price=p,fee=fee,cost=cost)
    def sell(self,event,token,qty,price,ts):
        self._check(event,ts);q,p=dec(qty),dec(price)
        pos=self.positions.get(token)
        if not pos or q<=0 or q>pos["qty"] or not 0<p<1: raise ValueError("INVALID_SELL")
        fee=self.policy.fee(q,p);basis=pos["cost"]*q/pos["qty"];proceeds=q*p
        if self.cash+proceeds-fee<self.reserved: raise ValueError("INSUFFICIENT_FEE_CASH")
        self.cash+=proceeds-fee;self.realized+=proceeds-basis-fee
        pos["qty"]-=q;pos["cost"]-=basis;self.fees+=fee;self.turnover+=proceeds
        self._record(event,ts,"SELL",token=token,qty=q,price=p,fee=fee,basis=basis)
    def settle(self,event,token,payout,ts,available_ts,source):
        self._check(event,ts);p=dec(payout)
        if not source or not isinstance(available_ts,int) or not 0<=available_ts<=ts or p not in (ZERO,Decimal(1)): raise ValueError("INVALID_SETTLEMENT")
        pos=self.positions.get(token)
        if not pos or pos["qty"]<=0: raise ValueError("NO_OPEN_POSITION")
        proceeds=pos["qty"]*p;self.cash+=proceeds;self.realized+=proceeds-pos["cost"]
        self.positions[token]={"qty":ZERO,"cost":ZERO}
        self._record(event,ts,"SETTLEMENT",token=token,payout=p,source=source,available_ts_ms=available_ts)
    def mark(self,net_unit_marks):
        active={t:p for t,p in self.positions.items() if p["qty"]>0}
        unknown=sorted(set(active)-set(net_unit_marks))
        values={t:dec(net_unit_marks[t]) for t in active if t in net_unit_marks}
        if any(not 0<=v<=1 for v in values.values()): raise ValueError("INVALID_MARK")
        basis=sum((p["cost"] for p in active.values()),ZERO)
        value=None if unknown else sum((active[t]["qty"]*v for t,v in values.items()),ZERO)
        equity=None if value is None else self.cash+value
        unreal=None if value is None else value-basis
        if equity is not None and abs(equity-(self.initial+self.realized+unreal))>Decimal("1e-20"):
            raise AssertionError("EQUITY_CONSERVATION")
        return {"status":"UNRESOLVED_POSITION" if unknown else "COMPLETE",
                "unresolved":unknown,"initial":self.initial,"cash":self.cash,
                "reserved":self.reserved,"available":self.available,
                "realized":self.realized,"unrealized":unreal,"equity":equity,
                "open_cost":basis,"fees":self.fees,"turnover":self.turnover}

class BookTape:
    """Causal observations and persistent counterfactual liquidity, per token/side.

    Production must also validate market/generation/expiry and each side's clocks.
    This primitive never asserts that a new snapshot supplies fresh liquidity.
    """
    def __init__(self):
        self.books={};self.depth={};self.ids=set();self.last=-1
    def observe(self,event,token,source,received,available,asks,bids):
        if event in self.ids: raise ValueError("DUPLICATE_EVENT")
        if not all(isinstance(t,int) for t in (source,received,available)) or not 0<=source<=received<=available:
            raise ValueError("FUTURE_TIMESTAMP")
        if available<self.last: raise ValueError("OUT_OF_ORDER_EVENT")
        fresh={}
        for side,levels in (("BUY",asks),("SELL",bids)):
            vis={}
            for price,qty in levels:
                p,q=dec(price),dec(qty)
                if not 0<p<1 or q<0 or p in vis: raise ValueError("INVALID_DEPTH")
                vis[p]=q
            prior=self.depth.get((token,side),{})
            fresh[(token,side)]={p:(q,min(q,prior.get(p,(ZERO,ZERO))[1]+max(ZERO,q-prior.get(p,(ZERO,ZERO))[0]))) for p,q in vis.items()}
            # Keep zero levels as tombstones: removal does not itself replenish.
            for p in set(prior)-set(vis): fresh[(token,side)][p]=(ZERO,ZERO)
        self.depth.update(fresh);self.ids.add(event);self.last=available
        self.books.setdefault(token,[]).append({"event_id":event,"token":token,"source_ts_ms":source,"receive_ts_ms":received,"available_ts_ms":available})
    def at(self,token,now):
        return next((b.copy() for b in reversed(self.books.get(token,[])) if b["available_ts_ms"]<=now),None)
    def sweep(self,token,side,qty,now):
        q=dec(qty)
        if side not in ("BUY","SELL") or q<0: raise ValueError("INVALID_SWEEP")
        latest=self.books.get(token,[])
        if not latest or latest[-1]["available_ts_ms"]>now: raise ValueError("FUTURE_BOOK")
        result=[];depth=self.depth[token,side]
        for p in sorted(depth,reverse=side=="SELL"):
            visible,remaining=depth[p];take=min(q,remaining)
            if take>0: result.append((p,take));depth[p]=(visible,remaining-take);q-=take
            if not q: break
        return result

@dataclass(frozen=True)
class PartitionPlan:
    start:int
    durations:tuple
    embargo:int
    def __post_init__(self):
        if len(self.durations)!=3 or any(x<=self.embargo for x in self.durations) or self.embargo<0:
            raise ValueError("INVALID_BOUNDARIES")
    def classify(self,market_start,market_end,feature_start,label_end):
        if not feature_start<=market_start<market_end<=label_end: raise ValueError("INVALID_INTERVAL")
        lo=self.start
        for i,(name,duration) in enumerate(zip(("TRAIN","VALIDATION","OOS"),self.durations)):
            hi=lo+duration
            if market_start>=lo+(self.embargo if i else 0) and market_end<=hi and feature_start>=lo+(self.embargo if i else 0) and label_end<=hi:
                return name
            lo=hi
        return "PURGED"

@dataclass(frozen=True)
class Seal:
    hashes:dict
    @classmethod
    def create(cls,root,names):
        root=Path(root).resolve();values={}
        for n in sorted(names):
            p=(root/n).resolve()
            if not p.is_relative_to(root) or not p.is_file(): raise ValueError("INVALID_SEAL_PATH")
            values[n]=file_hash(p)
        return cls(values)
    def verify(self,root):
        root=Path(root).resolve()
        for n,h in self.hashes.items():
            p=(root/n).resolve()
            if not p.is_relative_to(root) or not p.is_file() or file_hash(p)!=h: raise ValueError("HASH_MISMATCH:"+n)
    @property
    def hash(self): return digest(self.hashes)

class AccessGate:
    """Durable exclusive first-access markers. No dataset loader is supplied here.

    A crash consumes access; no automatic retry. Hashes and upstream results are
    bound into each marker. This is an audit guard, not a filesystem security ACL.
    """
    def __init__(self,directory,root,seal,dataset_hash):
        self.directory=Path(directory);self.root=Path(root);self.seal=seal;self.dataset_hash=dataset_hash
    def _read(self,name):
        p=self.directory/name
        if not p.exists(): raise ValueError("PREREQUISITE_MISSING:"+name)
        try:return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError,OSError) as e:raise ValueError("INVALID_PREREQUISITE") from e
    def open(self,split,dataset_hash,freeze):
        safety()
        names=("TRAIN","VALIDATION","OOS")
        if split not in names: raise ValueError("INVALID_SPLIT")
        self.seal.verify(self.root)
        if dataset_hash!=self.dataset_hash: raise ValueError("DATASET_HASH_MISMATCH")
        prior_hash=None
        if split!="TRAIN":
            prev=names[names.index(split)-1]
            result=self._read(prev+"_RESULT.json");marker=self._read(prev+"_FIRST_ACCESS.json")
            if result.get("verdict")!="PASS" or result.get("marker_hash")!=digest(marker) or marker.get("seal_hash")!=self.seal.hash or marker.get("dataset_hash")!=dataset_hash:
                raise ValueError("UPSTREAM_NOT_PASS_OR_CHANGED")
            prior_hash=digest(result)
        payload={"split":split,"timestamp_ns":time.time_ns(),"pid":os.getpid(),
                 "seal_hash":self.seal.hash,"dataset_hash":dataset_hash,
                 "freeze_hash":digest(freeze),"freeze":json.loads(encode(freeze)),"upstream_result_hash":prior_hash,**safety()}
        write_once(self.directory/(split+"_FIRST_ACCESS.json"),payload)
        return payload
    def finish(self,split,verdict,result):
        safety();self.seal.verify(self.root)
        if split not in ("TRAIN","VALIDATION","OOS"): raise ValueError("INVALID_SPLIT")
        if verdict not in ("PASS","FAIL","INCONCLUSIVE"): raise ValueError("INVALID_VERDICT")
        marker=self._read(split+"_FIRST_ACCESS.json")
        if marker["seal_hash"]!=self.seal.hash or marker["dataset_hash"]!=self.dataset_hash: raise ValueError("FREEZE_CHANGED")
        write_once(self.directory/(split+"_RESULT.json"),{"verdict":verdict,"result":result,"marker_hash":digest(marker)})

def qualification(summary,criteria):
    """Classify already computed, audited metrics; missing/invalid evidence is not FAIL."""
    gates=criteria["data_gates"]
    if any(summary.get(g) is not True for g in gates): return "INCONCLUSIVE"
    samples={"opportunities":"opportunities_min","filled_entries":"filled_entries_min",
             "markets_with_fills":"markets_with_fills_min","active_6h_blocks":"active_6h_blocks_min"}
    try:
        if any(dec(summary[k])<dec(criteria[v]) for k,v in samples.items()): return "INCONCLUSIVE"
        if dec(summary["coverage"])<dec(criteria["coverage_min"]): return "INCONCLUSIVE"
        checks=[dec(summary[k])>0 for k in ("gross_pnl","net_pnl","net_without_best_market","expectancy_lower","expectancy_lower_sensitivity")]
        checks.append(0<=dec(summary["max_drawdown_fraction"])<=dec(criteria["max_drawdown_fraction"]))
    except (KeyError,ValueError,ArithmeticError,TypeError): return "INCONCLUSIVE"
    return "PASS" if all(checks) else "FAIL"
