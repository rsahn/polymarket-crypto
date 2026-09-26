"""Fee evidence diagnostics only. Never upgrades unknown rounding to qualified."""
from decimal import Decimal,ROUND_HALF_EVEN,ROUND_DOWN
from .core import dec
from .engine import FeeQualification

def diagnose_market(gamma,clob,source,version):
    records=[]
    import json
    tokens=gamma.get("clobTokenIds",[])
    if isinstance(tokens,str):tokens=json.loads(tokens)
    fd=clob.get("fd") or {}
    for token in tokens:
        record=FeeQualification.from_evidence(gamma,token,source=source,version=version).record()
        clob_tokens=[t.get("t") for t in clob.get("t",[])]
        match=(gamma.get("conditionId")==clob.get("c") and token in clob_tokens and
            dec(fd.get("r","-1"))==dec((gamma.get("feeSchedule") or {}).get("rate","-2")) and
            fd.get("e")==(gamma.get("feeSchedule") or {}).get("exponent") and fd.get("to") is True)
        record["public_sources_agree"]=match
        record["clob_version_field"]=clob.get("v")
        record["exact_aggregation"]="UNPROVEN"
        record["exact_partial_fill_rounding"]="UNPROVEN"
        if not match:record["reasons"]=tuple(record["reasons"])+("PUBLIC_FEE_SOURCES_DISAGREE",)
        record["qualification_status"]="MARKET_FEE_UNQUALIFIED"
        records.append(record)
    return records

def ambiguity_example():
    # Competing calculations, NOT candidates admitted into the production policy.
    raw=dec(".002")*dec(".07")*dec(".5")*dec(".5")
    unit=Decimal(".00001")
    return {"raw_per_fill":str(raw),
        "two_fills_round_each_half_even":str(raw.quantize(unit,rounding=ROUND_HALF_EVEN)*2),
        "two_fills_aggregate_then_half_even":str((raw*2).quantize(unit,rounding=ROUND_HALF_EVEN)),
        "round_down_per_fill":str(raw.quantize(unit,rounding=ROUND_DOWN)),
        "production_rule":"UNPROVEN"}
