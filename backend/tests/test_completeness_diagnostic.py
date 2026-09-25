def test_latency_cannot_resolve_post_c_completeness():
    from test_fixed_boundary import evidence
    from app.live.fixed_boundary import evaluate_boundary
    from analysis.qualify_post_genesis import inventory_completeness
    for now, stale in [(1300,False),(2000,True)]:
        proof=evaluate_boundary(evidence(),now=now)
        diagnostic=inventory_completeness({'post_b_proof':proof})
        assert diagnostic['inventory_through_C_proven']
        assert diagnostic['current_inventory_proven'] is False
        assert diagnostic['post_C_completeness']=='UNPROVEN_NO_COMMON_WATERMARK'
        assert diagnostic['generation_stale'] is stale
        assert diagnostic['latency_fix_sufficient'] is False


def test_missing_proof_is_not_presented_as_coverage():
    from analysis.qualify_post_genesis import inventory_completeness
    result=inventory_completeness(None)
    assert not result['evidence_available']
    assert not result['inventory_through_C_proven']
    assert not result['current_inventory_proven']
