# D6 final path: transport reuse and WS reader liveness

## Causal DAG retained
Before and after: prepared anchor -> select C once -> fixed tail -> seal C -> [balance || orders || trades || positions] -> [canonical B || canonical C] -> reconciliation -> live WS sample -> evaluation -> durable checkpoint.

The second group is a temporal witness AFTER all account observations, not merely a computation using their results. Running it concurrently permits a reorg after that witness but before the final account response. test_final_dag.py contains the deterministic counterexample. No account/recheck overlap is claimed or introduced. Parallel account reads and parallel B/C reads remain intact.

## Measured budget (target report 163524)
Inventory scan 597 ms; seal 220 ms; account group 293 ms (individual GETs 213/224/232/245 ms); canonical group 267 ms; reconciliation/evaluation 11 ms. Account age at evaluation 571 ms; original inventory acquisition age 1388 ms. Network AFTER values are NOT MEASURED: no target qualification executed here. No p95/p99 claim or guaranteed <500 ms.

Existing final DAG timestamps are retained. HTTPX persistent clients now retain bounded pools (8 connections), with connect/TLS counters and actual network-stream identity reuse evidence in each request. Fake tests prove client reuse and boundary enforcement; only the target report can prove real socket reuse and latency. Existing proxy configuration selects the original urllib path before any request; no proxy bypass, no retry/fallback after failure. Request URLs/headers and trace detail are never retained in pool diagnostics. RPC allows only existing read methods; CLOB remains GET-only. Pools close after qualification. No checkpoint precedes evaluation.

## Inventory contract unchanged
Coverage <=C is durable historical coverage, subject to canonical hash validation. A later hash recheck proves canonical identity, not reacquisition of inventory or completeness after C. Original acquisition timestamps remain unchanged. The existing boundary-generation gate still checks real acquisition ages; neither seal nor recheck refreshes them. Credential-view/indexer observations do not establish a common post-C completeness watermark. current_inventory_proven remains fail-closed, even if transport latency improves. Fixed-C, risk, signal and freshness files were not changed.

## WS bug and separate correction
A wire event received at age 500 ms can reach BookStateSource.update at 501 ms and raise STALE_BOOK. The receive loop previously continued for STALE_WIRE_EVENT but not STALE_BOOK. The latter stopped receiving and entered context shutdown; connected could remain true during close timeout. The deterministic regression fails before the fix and passes afterward.

STALE_BOOK now invalidates both token books but keeps the receive loop running. Two new full snapshots are required to resynchronize. A connected socket never grants economic freshness. PONG receipt is separately recorded, without refreshing book timestamps. Diagnostics retain source/receipt times, local processing delay, frame/PONG receipt, and no-new-wire over 500 ms. A stale event at receipt is distinguished from crossing the limit during local processing. No absent side is synthesized. BOOK_REGRESSION and pre-snapshot -15/-16 ms behavior are unchanged and fail-closed.

## Validation
RED.log records both initial failures (missing pool and reader stopping). GREEN.log records initial targeted success; TESTS_COMPLETE.log is authoritative final result: 617 passed, 8 subtests passed, 3 warnings. Audit passed; 16 SDK monetary methods guarded, zero monetary attempts, no external socket attempts. VALIDATION.json records protected-file comparisons and scoped pattern scan (not a global secret-absence claim). Genesis snapshot is unchanged, event count zero. Flags false, monetary transport locked. No network qualification, credentials or private keys loaded by this work.

## Manual target qualification
Run from repository root in the existing configured PowerShell session:

    python -B .\analysis\qualify_post_genesis.py --target-machine --health-contract

Return the newly printed D6_POST_GENESIS_READINESS report filename. Do not arm or submit.
