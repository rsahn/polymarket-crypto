"""Read-only readiness inspection. No T0 binding, collection or economic evaluation."""
import argparse
import json
import shutil
import hashlib
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from .core import dec, file_hash, safety
from .prepare import EXPECTED

def storage_estimate(observed_bytes,seconds,free_bytes,*,hours=168,journal_bytes=None,checkpoint_bytes=None):
    if observed_bytes<=0 or dec(seconds)<=0: raise ValueError("INVALID_STORAGE_EVIDENCE")
    dataset=int((dec(observed_bytes)/dec(seconds)*hours*3600).to_integral_value(rounding=ROUND_CEILING))
    # Engineering reserve chosen before new data: 2x observed throughput, plus 20%.
    # It is not a demonstrated worst-case bound for a future week.
    known_journal=journal_bytes is not None and checkpoint_bytes is not None
    reserve=int(((dec(dataset)*2+dec(journal_bytes or 0)+dec(checkpoint_bytes or 0))*dec("1.2")).to_integral_value(rounding=ROUND_CEILING))
    reasons=[] if known_journal else ["DISK_CAPACITY_UNPROVEN"]
    if free_bytes<reserve: reasons.append("DISK_SPACE_INSUFFICIENT")
    return {"observed_bytes":observed_bytes,"observed_seconds":str(seconds),
        "dataset_bytes":dataset,"free_bytes":free_bytes,"journal_bytes":journal_bytes,
        "checkpoint_bytes":checkpoint_bytes,"safety_factor":"2x observed + 20% margin",
        "required_bytes_lower_bound":reserve,"reasons":reasons}

def preflight(root,evidence):
    root=Path(root); evidence=Path(evidence); flags=safety(); checks={}; reasons=[]
    for p,h in EXPECTED.items(): checks[p]=file_hash(root/p)==h
    baseline=root/"analysis/d6/prospective_v1/evidence/baseline_20260926/STRATEGY_MANIFEST.json"
    saved=json.loads(baseline.read_text(encoding="utf-8"))
    checks["criteria_hash"]=file_hash(root/"analysis/d6/prospective_v1/criteria.json")==saved["criteria_hash"]
    manifest=root/"analysis/d51/smoke_20260922_194254/review/RUN_MANIFEST.json"
    collection=root/"analysis/d51/smoke_20260922_194254/COLLECTION_RESULT.json"
    obs=json.loads(manifest.read_text()); captured=json.loads(collection.read_text())
    storage=storage_estimate(obs["source_stat_before"][0],captured["collection_seconds"],shutil.disk_usage(root).free)
    reasons.extend(storage["reasons"])
    report=evidence/"VALIDATION.json"
    validation=json.loads(report.read_text()) if report.exists() else {}
    source_hashes=validation.get("source_hashes",{})
    source_sealed=bool(source_hashes) and all((root/p).is_file() and file_hash(root/p)==h for p,h in source_hashes.items())
    log=evidence/"FULL_SUITE.log"
    log_proven=log.is_file() and file_hash(log)==validation.get("full_suite_log_sha256")
    checks["full_suite"]=source_sealed and log_proven and validation.get("full_suite_failures")==0 and validation.get("full_suite_exit_code")==0
    checks["validated_source_seal"]=source_sealed
    checks["ledger_synthetic_integration"]=checks["full_suite"]
    checks["journal_fsync_crash_recovery"]=checks["full_suite"]
    checks["monetary_sdk_zero"]=validation.get("sdk_monetary_attempts")==0
    # Until a seal-bound completed integration proof exists these fail closed.
    checks.update({"dependency_seal":False,"fee_qualification":False,"causal_adapter":False,
                   "ledger_production_binding":False,
                   "partition_manifest":False,"freeze":False,"oos_lock_ready":False,
                   "clock_sanity":False})
    reasons.extend(["MARKET_FEE_UNQUALIFIED:ROUNDING_AND_FUTURE_MARKET_EVIDENCE",
        "V1_ENTRY_CALLBACK_MISSING_ON_EXIT_FAILURE",
        "V1_OBSERVED_FILLS_MAY_REUSE_COUNTERFACTUAL_DEPTH",
        "ABSOLUTE_BOUNDARIES_UNBOUND",
        "CURRENT_TWO_REFERENCE_CLOCK_EVIDENCE_MISSING",
        "PRODUCTION_BINDING_AND_DEPENDENCY_SEAL_PENDING"])
    if not checks["journal_fsync_crash_recovery"]: reasons.append("WRITE_DURABILITY_UNPROVEN")
    reasons.extend("CHECK_FAILED:"+k for k,v in checks.items() if not v)
    return {"name":"BTC_V1_PROSPECTIVE_PREFLIGHT","status":"BLOCKED" if reasons else "READY",
        "reasons":sorted(set(reasons)),"checks":checks,"storage":storage,
        "storage_evidence_hashes":{str(manifest.relative_to(root)):file_hash(manifest),
                                   str(collection.relative_to(root)):file_hash(collection)},
        "SYSTEM_READY":False,"current_inventory_proven":False,
        "collection_started":False,"TRAIN_opened":False,"VALIDATION_opened":False,"OOS_opened":False,**flags}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--evidence",type=Path,required=True)
    a=p.parse_args(); result=preflight(a.root,a.evidence); print(json.dumps(result,indent=2)); return 0 if result["status"]=="READY" else 2
if __name__=="__main__":raise SystemExit(main())
