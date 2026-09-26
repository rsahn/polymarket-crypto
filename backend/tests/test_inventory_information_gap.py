"""Counterexample: identical supplied observations cannot exclude unseen transfers."""
from copy import deepcopy
from app.live.fixed_boundary import evaluate_boundary
from app.live.freshness_policy import freshness_policy
from test_fixed_boundary import evidence


def test_unseen_post_boundary_transfer_cannot_be_certified_absent():
    # Both worlds expose exactly the same fixed-C scan and lagging indexer views.
    # A third-party ERC1155 transfer at C+1 does not require D6 to submit an order.
    quiet=evidence()
    transfer_after_C=deepcopy(quiet)
    with freshness_policy(1300):
        for observation in (quiet,transfer_after_C):
            result=evaluate_boundary(observation,now=1300)
            assert result['inventory_through_C_proven']
            assert result['boundary_generation_complete']
            assert not result['current_inventory_proven']
            assert not result['ready_for_arm']
            assert not result['submit_allowed']
            assert result['reason']=='POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN'
    assert quiet==transfer_after_C
