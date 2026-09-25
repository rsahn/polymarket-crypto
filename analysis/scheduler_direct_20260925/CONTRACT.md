# Direct readiness scheduling, 2026-09-25

Reference: D6_POST_GENESIS_READINESS_20260925_171636_625980.json.

## Cause and unchanged causal order
Call graph: qualify_post_genesis.run -> run_generation_worker -> acquire_post_b -> await fresh_views(client) -> await recheck_fixed_boundary -> evaluate_boundary -> return -> reconciliation -> ProductionReadinessCheck.run. The exact serialization is two consecutive awaits in acquire_post_b. Four account reads overlap inside fresh_views; two numeric B/C reads overlap inside recheck_fixed_boundary. These groups do NOT overlap: the canonical witness is required AFTER account completion to catch reorg during GETs. Existing deterministic counterexample in test_final_dag.py remains valid. No fake concurrent-group field or test claims safe overlap.

## Removed experiment
The prior isolated loop attempted to reduce WS event-loop contention. Last target run demonstrated 32ms shutdown plus 89ms cross-thread/main resumption before reconciliation. That isolation protects no business invariant and is removed. run_generation_worker retains its API name but now schedules a bounded coroutine on the existing runner loop. There is no asyncio.run, new loop, thread handoff, or loop shutdown per generation. Shield/drain remains to avoid closing HTTP transports while bounded read work is running on cancellation. This leaves an ordinary same-loop task continuation, which is timed honestly; zero continuation latency is not promised. WS/parser/resync unchanged.

## DAG
Before: fixed tail/seal -> parallel account -> parallel B/C -> bounded validation -> private loop shutdown -> cross-thread return -> reconciliation -> book sample -> readiness -> persistence.
After: fixed tail/seal -> parallel account -> parallel B/C -> bounded validation -> same-loop continuation -> reconciliation -> book sample -> readiness -> metadata formatting/persistence -> final cleanup.
Readiness authority remains ProductionReadinessCheck, called once. The latest in-memory WS is sampled by that authority. Ledger reads retained before evaluation for concurrent mutation detection. Inventory metadata formatting deferred after decision. No reports or checkpoints before evaluation; atomic checkpoint publication remains after decision, with previous verified cursor retained on crash. No stale cursor becomes fresh and no historical Genesis scan is introduced.

## Measurements
BEFORE inventory1032/account595/book93ms, critical1190ms. Account266 + recheck147 =413ms sequential. Post-proof182ms includes loop shutdown32, cross-thread resume89, reconciliation/final work61. Removing121ms alone is only a counterfactual, not a PASS proof; inventory was already850ms at proof completion.
AFTER target NOT RUN. Structurally no per-generation loop shutdown or cross-thread return exists. New scheduler_timing consolidates generation, scan completion, account/recheck, join, reconciliation, book sample, evaluation and persistence timestamps. Separate scan-resume and generation-continuation delays are measured. scheduler_overhead_before_evaluation_ms is null with explicit scope: total scheduler cost cannot honestly be isolated from business CPU using these observations. No latency percentile or claim of 350-400ms.

## Pools and inventory worker
Existing HTTPX pools remain alive through the run and close after decision/report construction. Warm TCP/TLS before any HTTP business request is not implemented: no supported public preconnect primitive has been established for installed HTTPX0.28.1, and private socket injection is not introduced. All four account reads occur anew; no old data used. This one-shot runner is not a running24/7 service. Existing verified cursor + anchor catch-up outside final path + minimal fixed tail is retained. A future single-owner permanent inventory task must publish immutable verified checkpoints, verify cursor hashes on restart, reject conflicts/gaps/reorgs and never refresh old observations. No permanent worker or extra scans launched in this iteration.

## Remaining proof limitation
Fixed-C evaluator unchanged: inventory_through_C_proven is not current_inventory_proven. Even a fresh bounded generation cannot establish a common post-C completeness boundary absent from the available remote sources. This scheduler change does not remove that fail-closed block or guarantee SYSTEM_READY.

## Validation
RED proves old isolated loop differs from runner loop. GREEN and full suite validate same-loop execution, original observation retention, propagated failure, cancellation drain, fail-closed early failure report, plus existing fixed-C canonical/partial/stale tests and frozen WS tests. Audit and scoped pattern scan recorded separately. No authenticated network, secrets or private keys loaded. Flagsfalse; no monetary call.
