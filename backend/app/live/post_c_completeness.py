"""Diagnostic only: current sources do not attest a common causal cut.

This module is NOT a positive proof verifier. Unknown remote boundaries stay
null even if caller metadata contains asserted watermarks. See the audited
invariant in analysis/post_c_completeness_20260926/POST_C_SOURCE_MATRIX.md.
"""
import re


def current_inventory_diagnostic(inventory=None, *, catchup=None):
    """Describe existing scoped evidence without acquiring or authorizing anything.

    inventory must come from the current generation; catchup is a completed
    bootstrap report. Neither supplies a new post-C observation boundary W.
    """
    inv = inventory if isinstance(inventory, dict) else {}
    proof = inv.get('post_b_proof', {})
    evidence = inv.get('boundary_evidence', {})
    proof = proof if isinstance(proof, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    c = c_hash = start = canonical = balance_block = None
    provenance = 'NO_CURRENT_GENERATION_EVIDENCE'
    if proof.get('inventory_through_C_proven') is True:
        c, c_hash = inv.get('to_block'), inv.get('block_hash')
        start = inv.get('from_block')
        canonical = (evidence.get('boundary_number') == c
                     and evidence.get('boundary_hash') == c_hash
                     and evidence.get('boundary_rechecked_hash') == c_hash)
        provenance = 'CURRENT_GENERATION_SCOPED_C'
    elif isinstance(catchup, dict) and catchup.get('status') == 'PASS_SCOPED_CATCHUP' and catchup.get('inventory_through_C_proven') is True:
        target = catchup.get('target_boundary', {})
        if isinstance(target, dict) and catchup.get('cursor_end') == target.get('number'):
            c, c_hash = target.get('number'), target.get('hash')
            previous = catchup.get('cursor_start')
            start = previous + 1 if type(previous) is int else None
            # Success is emitted only after catch_up's final numeric hash check.
            canonical = True
            provenance = 'BOOTSTRAP_SCOPED_C_NOT_A_DECISION_GENERATION'
    if type(c) is not int or c < 0 or not isinstance(c_hash, str) or not re.fullmatch(r'0x[0-9a-f]{64}', c_hash):
        c = c_hash = start = canonical = None
        provenance = 'NO_VALID_SCOPED_BOUNDARY_METADATA'
    elif canonical:
        balance_block = c
    return dict(
        status='CURRENT_INVENTORY_PROOF_IMPOSSIBLE_WITH_CURRENT_SOURCES',
        current_inventory_proven=False, SYSTEM_READY=False, ready_for_arm=False,
        submit_allowed=False, C=c, W=None, C_hash=c_hash, W_hash=None,
        onchain_coverage_start=start, onchain_coverage_end=c,
        gaps='UNKNOWN', canonical_recheck=canonical, balance_block=balance_block,
        clob_boundary=None, trades_boundary=None, orders_boundary=None,
        positions_boundary=None, indexer_boundary=None, common_watermark=None,
        omitted_interval=dict(after_block=c, through='GENERATION_DECISION_UNKNOWN_CUT',
                              remote_lower_bound='UNKNOWN', closure='UNPROVEN'),
        proof_reason='NO_COMMON_POST_C_COMPLETENESS_WATERMARK',
        missing_capabilities=[
            'CLOB_SCOPE_COMPLETE_SEQUENCE_AND_CHAIN_SETTLEMENT_LINK',
            'POSITIONS_PAGE_TO_SERVING_INGESTION_BOUNDARY_BINDING',
            'POST_W_TO_DECISION_MUTATION_CLOSURE'],
        provenance=provenance,
        scope='IDENTIFIED_CTF_ONLY_NOT_GLOBAL_INVENTORY',
        post_C_scan_performed=False,
        indexer_status_capability='PUBLIC_V2_STATUS_EXISTS_NOT_A_COMMON_CUT',
    )
