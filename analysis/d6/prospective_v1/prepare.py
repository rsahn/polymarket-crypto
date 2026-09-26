"""Capture a preparation baseline; deliberately has NO collection/evaluation mode."""
import argparse, importlib.metadata, json, platform, subprocess, sys, time
from pathlib import Path
from .core import Seal, file_hash, write_once, safety, digest

EXPECTED={
"analysis/d6/paper_live.py":"5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364",
"analysis/run_d6_paper_live.py":"a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405"}
def assert_identity(root):
    for name,wanted in EXPECTED.items():
        if file_hash(root/name)!=wanted: raise ValueError("STRATEGY_IDENTITY_CHANGED:"+name)
def prepare(root,destination):
    root=Path(root).resolve();destination=Path(destination).resolve();safety();assert_identity(root)
    if not destination.is_relative_to(root/"analysis/d6/prospective_v1"):
        raise ValueError("PREPARATION_OUTPUT_OUTSIDE_SCOPE")
    if destination.exists(): raise FileExistsError(destination)
    names=set(EXPECTED)
    names.add("analysis/d6/paper_live/STRATEGY_V1_FROZEN.json")
    for directory in ("backend/app","analysis/d6/prospective_v1"):
        for p in (root/directory).rglob("*"):
            if p.is_file() and p.suffix in (".py",".json",".sql",".md") and not p.is_relative_to(destination) and "__pycache__" not in p.parts and "evidence" not in p.parts:
                names.add(p.relative_to(root).as_posix())
    names.add("backend/requirements.txt")
    seal=Seal.create(root,names)
    git=lambda *a:subprocess.check_output(["git","--no-optional-locks",*a],cwd=root,text=True).strip()
    manifest={"phase":"PREPARATION","created_ns":time.time_ns(),"head":git("rev-parse","HEAD"),"branch":git("branch","--show-current"),
              "working_tree_status":git("status","--short").splitlines(),
              "strategy_hashes":EXPECTED,"dependency_superset":seal.hashes,"seal_hash":seal.hash,
              "python":platform.python_version(),"platform":platform.platform(),
              "packages":sorted({(d.metadata["Name"],d.version) for d in importlib.metadata.distributions() if d.metadata.get("Name")}),
              "criteria_hash":file_hash(root/"analysis/d6/prospective_v1/criteria.json"),
              "schema_hash":file_hash(root/"analysis/d6/prospective_v1/schema.json"),
              "identity_scope":"Current source closure and installed versions; not a historical validation attestation",
              "sizing":"FIXED25 primary; other sizes cannot affect it",**safety()}
    criteria=json.loads((root/"analysis/d6/prospective_v1/criteria.json").read_text())
    dataset={"phase":"PREPARATION_NOT_LAUNCHED","start_boundary":None,"planned_end_boundary":None,
             "boundary_status":"UNBOUND_BLOCKED_BEFORE_COLLECTION","planned_duration_hours":criteria["duration_hours"],
             "absolute_boundary_rule":"UTC five-minute boundary >=10min after all gates pass; freeze absolute boundaries before first capture",
             "timezone":"UTC; wall source/receive/availability plus actual monotonic attempt timing; no retiming",
             "sources":["Binance public BTC trades","Polymarket public BTC UP/DOWN 5m books","public market fees and confirmed resolutions"],
             "markets":"All prospectively registered BTC 5m slugs inside fixed boundaries; no outcome selection",
             "timeframes":["5m"],"partition_rules":"72h/48h/48h chronological, whole slug/condition, no shared market",
             "purge_rules":"Intervals crossing split boundary are excluded structurally before outcomes; unresolved held positions block rather than disappear",
             "embargo_ms":criteria["embargo_ms"],"schema_hash":manifest["schema_hash"],
             "collector_and_strategy_seal":seal.hash,"strategy_hashes":EXPECTED,
             "dataset_hash":None,"old_data_allowed":False,"collection_started":False}
    blockers=["MARKET_BOUND_FEE_AND_ROUNDING_EVIDENCE_MISSING","CAUSAL_V1_ADAPTER_AND_DURABLE_LEDGER_NOT_INTEGRATED",
              "SEALED_PARTITION_EVALUATOR_NOT_INTEGRATED","LOSSLESS_STORAGE_CAPACITY_UNQUALIFIED","ABSOLUTE_BOUNDARIES_UNBOUND","FULL_SUITE_NOT_GREEN_RETIRED_CANDIDATE_TESTS"]
    status={"status":"BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED","blockers":blockers,
            "SYSTEM_READY":False,"current_inventory_proven":False,
            "economic_evaluation_started":False,"collection_started":False,"oos_opened":False,**safety()}
    destination.mkdir(parents=True)
    write_once(destination/"STRATEGY_MANIFEST.json",manifest)
    write_once(destination/"DATASET_MANIFEST.json",dataset)
    write_once(destination/"STATUS.json",status)
    write_once(destination/"PREPARATION_SEAL.json",{"strategy_manifest_hash":file_hash(destination/"STRATEGY_MANIFEST.json"),
              "dataset_manifest_hash":file_hash(destination/"DATASET_MANIFEST.json"),"status_hash":file_hash(destination/"STATUS.json")})
    return status
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(prepare(a.root,a.out),indent=2))
    except (ValueError,OSError) as e: print(str(e),file=sys.stderr);return 2
    return 0
if __name__=="__main__":raise SystemExit(main())
