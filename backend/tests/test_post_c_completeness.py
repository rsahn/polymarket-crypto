"""No timing or fabricated completeness claim may create a capability."""
import copy
import hashlib
import json
from pathlib import Path
import pytest


def inventory():
    return dict(from_block=10,to_block=24,block_hash="0x"+"b"*64,
        post_b_proof=dict(inventory_through_C_proven=True,current_inventory_proven=False),
        boundary_evidence=dict(boundary_number=24,boundary_hash="0x"+"b"*64,
            boundary_rechecked_hash="0x"+"b"*64))


@pytest.mark.parametrize("claim",[
    {}, {"positions_received_ms":1000}, {"account_received_after_W":True},
    {"latest":25}, {"balances":{"token":"0"}}, {"timeout":False,"fresh":True},
    {"ranges":[[25,25],[27,28]]}, {"W_hash":"0x"+"c"*64},
    {"removed":True}, {"pagination_complete":False}, {"authenticated":False},
    {"source_timestamp_ms":9999999999999999},
    {"all_mutations_covered":True,"canonical":True,"account_complete":True,
     "common_watermark":28,"current_inventory_proven":True},
    {"freshness_limit_ms":500}, {"freshness_limit_ms":1300},
    {"indexer_status":{"ingestion":{"min_synced_block":28},"serving":{"lag_seconds":0}}},
])
def test_unbound_claims_never_create_current_proof(claim):
    from app.live.post_c_completeness import current_inventory_diagnostic
    e=inventory();e.update(claim);before=copy.deepcopy(e)
    r=current_inventory_diagnostic(e)
    assert e==before
    assert r["status"]=="CURRENT_INVENTORY_PROOF_IMPOSSIBLE_WITH_CURRENT_SOURCES"
    assert r["current_inventory_proven"] is False
    assert r["common_watermark"] is None and r["W"] is None
    assert not r["SYSTEM_READY"] and not r["ready_for_arm"] and not r["submit_allowed"]


def test_schema_preserves_known_C_without_inventing_W():
    from app.live.post_c_completeness import current_inventory_diagnostic
    r=current_inventory_diagnostic(inventory())
    assert r["C"]==24 and r["C_hash"]=="0x"+"b"*64
    assert r["canonical_recheck"] is True and r["balance_block"]==24
    for k in ("clob_boundary","trades_boundary","orders_boundary","positions_boundary","indexer_boundary","common_watermark","W","W_hash"):
        assert r[k] is None
    assert r["omitted_interval"]["after_block"]==24
    assert r["gaps"]=="UNKNOWN"


@pytest.mark.parametrize("e",[None,{},[],{"post_b_proof":{}},
    {"post_b_proof":{"inventory_through_C_proven":False},"to_block":24}])
def test_no_generation_does_not_relabel_preparation(e):
    from app.live.post_c_completeness import current_inventory_diagnostic
    r=current_inventory_diagnostic(e)
    assert r["C"] is None and r["canonical_recheck"] is None


def test_catchup_keeps_success_scoped():
    from app.live.post_c_completeness import current_inventory_diagnostic
    e=dict(status="PASS_SCOPED_CATCHUP",inventory_through_C_proven=True,cursor_start=20,
           cursor_end=24,target_boundary=dict(number=24,hash="0x"+"b"*64))
    r=current_inventory_diagnostic(catchup=e)
    assert r["C"]==24 and r["onchain_coverage_start"]==21
    assert not r["current_inventory_proven"] and e["status"]=="PASS_SCOPED_CATCHUP"
    e["status"]="BLOCKED"
    assert current_inventory_diagnostic(catchup=e)["C"] is None


def test_changed_C_hash_is_not_canonical():
    from app.live.post_c_completeness import current_inventory_diagnostic
    e=inventory();e["boundary_evidence"]["boundary_rechecked_hash"]="0x"+"c"*64
    r=current_inventory_diagnostic(e)
    assert r["canonical_recheck"] is False and not r["current_inventory_proven"]


def test_protected_genesis_btc_risk_flags_unchanged():
    root=Path(__file__).resolve().parents[2]
    baseline=json.loads((root/"analysis/post_c_completeness_20260926/BASELINE.json").read_text())
    for name,expected in baseline["protected"].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
    assert set(baseline["flags"].values())=={"false"}


def test_worker_report_contains_fail_closed_proof(tmp_path, monkeypatch):
    import analysis.run_inventory_catchup as q
    folder=tmp_path/"runtime";folder.mkdir();(folder/"d6_genesis.db").write_bytes(b"fixture")
    monkeypatch.setattr(q,"read_genesis",lambda p:dict(phase="NOT_RECONCILED"))
    r=q.cycle(tmp_path,"https://example.invalid")
    assert r["current_inventory_proof"]["C"] is None
    assert not r["current_inventory_proof"]["current_inventory_proven"]
    assert not r["SYSTEM_READY"] and not r["submit_allowed"]


def test_offline_readiness_report_contains_unknown_boundaries(monkeypatch):
    import asyncio
    import analysis.qualify_post_genesis as q
    r=asyncio.run(q.run(False,health_contract=True))
    assert r["current_inventory_proof"]["common_watermark"] is None
    assert r["current_inventory_proof"]["C"] is None
    assert not r["current_inventory_proof"]["submit_allowed"]
