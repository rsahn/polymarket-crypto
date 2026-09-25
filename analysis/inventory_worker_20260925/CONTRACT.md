# Isolated inventory generation: contract and limits

Reference: D6_POST_GENESIS_READINESS_20260925_170653_660563.json.

## Freshness meaning
scan_observed_ms=1790356010691 is the real dispatch/acquisition START of the tail evidence, after checking the previous cursor. No inventory completeness property becomes true at that instant. It is a conservative lower bound on the acquisition interval, deliberately retained to prevent hiding time spent acquiring the oldest component. Scan completion proves requested CTF coverage, not current account completeness. Seal/recheck prove canonical identity, not a newer inventory acquisition. JOIN is a validation event, never a refresh of component observations.

Coverage <=C is durable while canonical. Current inventory after C additionally needs a common completeness boundary with account/indexer, which the available sources do not supply. fixed_boundary.py explicitly NEVER sets current_inventory_proven true. Passing its 500ms interval test certifies a bounded generation only; POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN remains. This work cannot promise SYSTEM_READY from latency optimization alone. No timestamp origin or contract was changed.

## DAG before and after
Logical dependencies unchanged; execution placement changes. Before, async scan/account/recheck orchestration shared the WS event loop. After, one bounded read-only generation runs on its own event loop in a worker thread. Shared HTTP clients are synchronous, bounded, thread-safe pools; audit collections are read after the worker joins. No WS object crosses the thread boundary. Cancellation drains the worker before HTTP pools close. No detached reads or retries. GIL contention is not eliminated; target timing must quantify the effect.

| Node | Inputs -> outputs / protected invariant | Timing/dependency and parallelism |
|---|---|---|
| Finalized B | provider tag -> qualified B/hash | pre-generation, no claim of independent consensus |
| Cursor verification | stored cursor+hash -> verified starting point | prior to catch-up, no rewind |
| Anchor catch-up | cursor+1..B -> gapless coverage | before final generation, existing durable cursor |
| C selection | latest once -> fixed C/header | after B, no head chasing |
| Tail B+1..C | chain/code/logs and discovered asset balances -> coverage | independent RPC reads parallel, balances depend on discovery |
| Completion/seal | final numeric C read after logs/balances -> canonical witness | reused witness, no redundant call; original timestamp retained |
| Account group | sealed C + existing L2 -> four fresh observations | balance/orders/trades/positions parallel |
| Canonical B/C | completed account group -> final hash witnesses | two reads parallel AFTER account to detect reorg during GETs |
| Reconciliation | ledger + all remote evidence -> scoped verdict | no partial generation or cached FLAT |
| Book sample | existing live WS -> decision snapshot | main loop, immediately before evaluation |
| Evaluation | all timestamps/proofs -> health/eligibility | 500ms unchanged; economic eligibility separate |
| Checkpoint | proven bounded coverage -> atomic new checkpoint | after evaluation, no Genesis mutation |

Account and rechecks remain sequential by design. A recheck at t268 followed by reorg t280 and final account response t291 cannot witness the reorg. Concurrent branching would weaken the established post-account witness contract. test_final_dag.py preserves this counterexample rather than asserting a false safe parallel PASS.

## Actual 938ms decomposition
Tail acquisition 10691 to final scan await return 11166: 475ms. Within it getLogs took 234ms; numeric seal 179ms; after seal response 11107 to orchestration resume11166:59ms. These network timings include local scheduling, not pure provider latency. Pool reports prove reused TCP/TLS, but cannot isolate network vs GIL/provider for the 234ms.
Account group11166..11528:362ms, including90ms before first GET start11256. Individual GET durations177/213/182/269ms. Rechecks11528..11616:88ms. Final reconciliation/sample/evaluation11616..11629:13ms. Total938ms. Five tail blocks only: reducing historical range is not the immediate issue. Reported critical wall1027ms includes prior cursor verification89ms.

New metrics: worker submission/start/result-ready/finished/main-resumed; dispatch delay; loop shutdown; main-resume delay. fixed_scan records its actual worker completion separately from coroutine resumption. This distinguishes the unexplained59ms queue/resume gap from work in the scan thread. Account phase start and individual GET starts remain available. AFTER network timings are NOT MEASURED; no target run occurred here, no p95 claim, no claim that all149ms of gaps are removable.

## Continuous inventory/checkpoint architecture prepared, not launched
Existing load_inventory_cursor and prepare_finalized_inventory already keep historical catch-up outside the fresh tail. Retain a SINGLE owner of cursor state: verify Genesis binding and checkpoint digest, reread canonical cursor hash on restart, advance contiguous ranges only, never publish on partial RPC/reorg/conflict. The isolated generation is the separation boundary for future service ownership. A future permanent worker must publish immutable versioned checkpoints; final generation selects one version, fixes C once and acquires missing ranges. Concurrent publications require conflict detection; loading old evidence never refreshes it. No permanent service, background scan, or new freshness inference is introduced. Tests for cursor/restart/conflict and fixed-C remain in the full suite.

## Transport warm-up
Not implemented. HTTPX0.28.1 Client has no public preconnect primitive verified here. Injecting raw TLS sockets into private pool internals is not a qualified optimization. Existing pools retained; no private API or alternate route, no preloaded balance/orders/trades/positions. Real target GET connection establishment remains observable. This limitation is explicit rather than a false reuse claim.

## Safety/evidence
RED tests failed for absent worker; GREEN tests verify separate loop/thread, unchanged observed_ms, failure propagation, and cancellation drain. Full suite includes generation500/501, missing/mixed proofs, canonical failures, cursor integrity/conflicts, market/health separation, and frozen WS regressions. No supersession rule change. No real credentials or private keys loaded in development. Flags false, submit disallowed, no monetary calls. See FULL.log/AUDIT.log/INVARIANTS.json. Only source reads and offline tests; next target run is manual.
