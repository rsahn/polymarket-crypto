"""Deterministic synthetic/offline evaluator of durable observations.

This module never finds, opens or evaluates data by itself. evaluate_partition
can consume only its sealed loader's one-shot access path.
"""
import math
import json
import random
from collections import defaultdict
from decimal import Decimal
from .core import dec, qualification
from .engine import ProspectiveEventAdapter

def confidence_bound(hours,block_hours,replicates,seed,quantile):
    n=len(hours)
    if n<2*block_hours or not hours: return None
    rng=random.Random(seed); values=[]
    for _ in range(replicates):
        sample=[]
        while len(sample)<n:
            start=rng.randrange(n)
            sample.extend(hours[(start+i)%n] for i in range(block_hours))
        sample=sample[:n]
        count=sum(x[1] for x in sample)
        if not count: return None
        values.append(sum((dec(x[0]) for x in sample),Decimal(0))/count)
    values.sort()
    # Prespecified discrete inverse empirical CDF, no interpolation.
    return values[max(0,math.ceil(float(dec(quantile))*replicates)-1)]

def evaluate(adapter,criteria,start_ms,end_ms,data_gates,expected_observations,received_observations):
    if end_ms<=start_ms or (end_ms-start_ms)%3600000: raise ValueError("CALENDAR_HOUR_BOUNDARIES_REQUIRED")
    rows=adapter.journal.records; accounts=adapter.accounting
    if any(not start_ms<=r["event_ts"]<=end_ms for r in rows): raise ValueError("OUTSIDE_PARTITION")
    n_hours=(end_ms-start_ms)//3600000
    hours=[[Decimal(0),0] for _ in range(n_hours)]
    by_market=defaultdict(Decimal); by_direction=defaultdict(Decimal)
    entries={}; closed=set(); net=Decimal(0); fees=Decimal(0)
    active=set(); peak=dec(criteria["initial_cash"]); drawdown=Decimal(0); equity_known=True; required_marks=set(); covered_marks=set()
    for e,a in zip(rows,accounts):
        i=min(n_hours-1,(e["event_ts"]-start_ms)//3600000)
        delta=dec(a["net_delta"]); net+=delta; fees+=dec(a["fee_delta"])
        hours[i][0]+=delta; by_market[e["market_id"]]+=delta; by_direction[e["direction"]]+=delta
        trade=e.get("trade_id")
        if e["kind"] in ("ENTRY_FILL","ENTRY_PARTIAL_FILL"):
            entries[trade]=e["market_id"]; active.add(i//6)
        if a.get("trade_closed") and trade not in closed and trade in entries:
            closed.add(trade); hours[i][1]+=1
        if e["kind"] in ("ENTRY_FILL","ENTRY_PARTIAL_FILL","EXIT_FILL","EXIT_PARTIAL_FILL","POSITION_SETTLED"):
            required_marks.add(e["event_ts"])
        if e["kind"]=="MARK" and a["equity"] is not None:
            covered_marks.add(e["event_ts"])
        equity=a["equity"]
        if equity is not None:
            equity=dec(equity); peak=max(peak,equity)
            drawdown=max(drawdown,(peak-equity)/peak)
    equity_known=required_marks.issubset(covered_marks)
    mark=adapter.ledger.mark(adapter.marks)
    open_positions=[t for t,p in adapter.ledger.positions.items() if p["qty"]>0]
    # Marks are not substitutes for resolved positions at a split boundary.
    complete=not open_positions and not adapter.ledger.reservations and adapter.ended
    gates={k:data_gates.get(k) is True for k in criteria["data_gates"]}
    gates["NO_UNRESOLVED_POSITIONS"]=complete
    gates["FULL_LEDGER_RECONCILIATION"]=complete and mark["equity"]==dec(criteria["initial_cash"])+net
    # Unmarked intraperiod positions prevent a proven equity drawdown.
    gates["DATASET_ADMISSIBLE"]=gates["DATASET_ADMISSIBLE"] and equity_known
    coverage=None
    if type(expected_observations)==int and expected_observations>0 and type(received_observations)==int and 0<=received_observations<=expected_observations:
        coverage=dec(received_observations)/expected_observations
    conf=criteria["confidence"]
    lower=confidence_bound(hours,conf["block_hours"],conf["replicates"],conf["seed"],conf["lower_quantile"])
    stress=confidence_bound(hours,conf["sensitivity_block_hours"],conf["replicates"],conf["seed"],conf["lower_quantile"])
    best=max(by_market.values(),default=Decimal(0))
    result={**gates,"sample_count":len(entries),"filled_entries":len(entries),
        "opportunities":sum(r["kind"]=="SIGNAL" for r in rows),
        "attempted_entries":sum(r["kind"]=="ENTRY_INTENT" for r in rows),
        "market_count":len(set(entries.values())),"markets_with_fills":len(set(entries.values())),
        "active_6h_blocks":len(active),"closed_trades":len(closed),"coverage":coverage,
        "gross_pnl":net+fees,"fees":fees,"net_pnl":net,
        "ROI":net/dec(criteria["initial_cash"]),
        "expectancy":None if not closed else net/len(closed),
        "max_drawdown_fraction":drawdown if equity_known else None,
        "best_market_contribution":best,"net_without_best_market":net-best,
        "expectancy_lower":lower,"confidence_bound":lower,"expectancy_lower_sensitivity":stress,
        "unresolved_positions":open_positions,"economic_status":"COMPLETE" if complete else "PARTITION_ECONOMIC_RESULT_INCOMPLETE",
        "data_integrity_status":"PASS" if all(gates.values()) else "INCOMPLETE",
        "by_hour":[{"hour":i,"net":p,"closed":c} for i,(p,c) in enumerate(hours)],
        "by_day":[sum((h[0] for h in hours[i:i+24]),Decimal(0)) for i in range(0,n_hours,24)],
        "by_market":dict(by_market),"by_direction":dict(by_direction),
        "by_liquidity":"UNQUALIFIED_WITHOUT_COMPLETE_V1_BOOK_OBSERVATIONS",
        "fills":sum(r["kind"] in ("ENTRY_FILL","ENTRY_PARTIAL_FILL","EXIT_FILL","EXIT_PARTIAL_FILL") for r in rows),
        "partial_fills":sum("PARTIAL_FILL" in r["kind"] for r in rows),
        "no_fills":sum(r["kind"] in ("ENTRY_NO_FILL","EXIT_NO_FILL") for r in rows),
        "turnover":adapter.ledger.turnover,"equity":mark["equity"]}
    result["verdict"]=qualification(result,criteria)
    return result

def evaluate_partition(loader,split,fees,gates,expected,received):
    criteria_path="analysis/d6/prospective_v1/criteria.json"
    if criteria_path not in loader.seal.hashes:
        raise ValueError("CRITERIA_NOT_IN_DEPENDENCY_SEAL")
    loader.verify()
    criteria=json.loads((loader.source_root/criteria_path).read_text(encoding="utf-8"))
    index=("TRAIN","VALIDATION","OOS").index(split)
    start_ms=loader.manifest["start"]+sum(loader.manifest["duration_hours"][:index])*3600000
    end_ms=start_ms+loader.manifest["duration_hours"][index]*3600000
    rows=loader.load(split)  # Marker is durably consumed before any data exposure.
    class ReplayJournal:
        records=rows
    adapter=ProspectiveEventAdapter(ReplayJournal(),fees,synthetic=loader.synthetic)
    result=evaluate(adapter,criteria,start_ms,end_ms,gates,expected,received)
    loader.gate.finish(split,result["verdict"],result)
    return result
