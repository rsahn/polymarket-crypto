# Phase 1 validation evidence

BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED. No prospective collection or OOS access.

RED: python -B -m unittest analysis.d6.prospective_v1.test_protocol -v
failed before core.py existed: ModuleNotFoundError:
analysis.d6.prospective_v1.core (1 loader error).
GREEN: the same command passed 25 synthetic tests; rerun after review fixes passed
25 tests in 0.408 seconds.

Full suite: all git-tracked test_*.py under backend/ and analysis/, excluding
vendor and preserved frozen/code_at_review snapshots; plus new test_protocol.py.
106 files through analysis/validate_execution.py (offline socket/SDK harness).
Result: 906 passed, 3 failed, 58 subtests passed, 3 DuckDB deprecation warnings,
58.08 seconds. See FULL_SUITE.log (native Windows output encoding).
Failures all from depth_cache_candidate_not_adopted/test_d51_depth_cache.py:
test_bytes_exact_for_both_schemas_mutation_and_signed_zero
test_capacity_eviction_and_clear
test_nonfinite_still_rejected_and_not_cached
Root error: Store.pack_depth absent, followed by Windows temporary DB cleanup
PermissionError. These files and backend Store were not changed by this task.
Do not call the complete suite green or silently exclude these failures.

OFFLINE_PROOF: external connections blocked=0 (no attempts), production transport
lock tests=3, monetary SDK attempts=0, guarded SDK methods=16.
REAL_ORDERS_ENABLED=false; LIVE_EXECUTION_ARMED=false in test harness.

New tests cover: official formula example (synthetic applicability),
unknown-fee block, partial/multiple fills, no fill, no exit liquidity/residual,
settlement, reservations, conservation, duplicate/out-of-order/future events,
causal selection, persistent depth, three boundaries/purge/embargo, code/dataset/
runner hash tamper, post-freeze modification, first access, parallel access race,
crash consumes access, upstream TRAIN/VALIDATION fail, OOS rerun rejection,
identity guard before writes, false live flags and PnL-positive-alone rejection.

Limits: synthetic kernels are not integration proof. The fee applicability,
causal V1 parity adapter, durable journaling, sealed-partition loader and metric
evaluator are not qualified. Production capture remains unavailable.
