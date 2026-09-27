# CAPTURE_24H_STORAGE_BLOCKED

Historical-source decision: **NEW_24H_CAUSAL_CAPTURE_REQUIRED**. The final targeted historical qualification is closed. The fallback technical collector, immutable causal journal, full-depth reconstruction, observation contract and tests are implemented in this folder. No24h capture, PAPER, LIVE, dataset partition or economic evaluation was launched.

## Requested deliverables

| Item | Evidence / result |
| --- | --- |
| 1 — Sources | Official Polymarket book/price and blockchain interfaces; PMXT v2 docs/catalog/public code; relevant Pendulum mirror. See [source qualification](../HISTORICAL_SOURCE_QUALIFICATION.md). |
| 2 — PMXT access | Correct catalog-derived September09T17 direct object403; archive-site TLS failure. Accessible documented mirror via206. No authentication bypass. |
| 3 — Historical sample | YES:4096 rows;6650397 bytes transferred;32MiB transfer budget. No24h download. |
| 4 — Schema |16 columns, exact physical schema in [sample evidence](HISTORICAL_BOOK_RECONSTRUCTION_TEST.json). |
| 5 — Depth | Schema supports full depth; sampled records contain0 book anchors, so reconstructible full depth in this sample=NO. |
| 6 — Time/order | Millisecond source and receive times; market/token/receive sort;1754 same-token receive ties; no verified sequence tie-breaker. |
| 7 — Reconstruction |9 token timelines, unanchored state_at(T); [timeline evidence](HISTORICAL_TIMELINE.json). |
| 8 — Overlap | None with local September full-depth captures. All requested comparison metrics remain null/unmeasurable, never fabricated matches. |
| 9 — Source verdict | NEW_24H_CAUSAL_CAPTURE_REQUIRED. This is a qualification failure, not a universal claim that historical depth is unavailable. |
| 10 — Causal contract | [Exact contract](../CONTRACT.md): signal, due/actual entry/exit, selected state IDs, full-depth replay references, source/receive/decision clocks, sequence, simulated fill decomposition/residuals, fees and source hashes. |
| 11 — R1 adoption | YES, its observation transform is reused inside separately versioned CAUSAL_CAPTURE_V1_R2, with EXIT_WAIT added; no D6 runtime entry-point adoption. |
| 12 — Differential | ECONOMIC_BEHAVIOR_IDENTICAL=true on fixtures; original AST restored by stripping observations. Normal/partial/no-entry/no-exit/rotation, signal boundaries, direction, lookback and cooldown compared. No wall-clock or statistical equivalence claim. |
| 13 — Storage bound | 115017882010 bytes, engineering quota envelope including scratch and20percent margin. |
| 14 — Free space | 45693329408 bytes at final read-only preflight. |
| 15 — Additional | **69324552602 bytes**, on the same volume or another adequately provisioned authorized destination. |
| 16 — Collector tests |22 tests in final full suite. Explicit duplicate-payload/same-state/restart audit also PASS. RED evidence and intermediate failed fixtures preserved; final GREEN log authoritative. |
| 17 — Full suite | **1033 PASS,98 subtests PASS,0 FAIL**,87.96s.3 preexisting DuckDB deprecation warnings. [Final log](FULL_SUITE_FINAL.log), [test inventory](VALIDATION_FINAL.json). |
| 18 — Audit/leaks | PASS:139 protected files unchanged; targeted PEM/literal-secret scan has no findings. [Audit](AUDIT.json). |
| 19 — BTC V1 | Economic statements and FIXED25 arithmetic unchanged. No depth model A/B/C selected. |
| 20 — Protocol | Existing24h protocol and criteria byte hashes unchanged; old72/48/48 preserved. |
| 21 — D6 | Inventory/Genesis/post-C/WS/risk/readiness/semantic implementation unchanged. SYSTEM_READY=false; current_inventory_proven=false. Historical D5 remains FAIL. |
| 22 — Flags | REAL_ORDERS_ENABLED=false; LIVE_EXECUTION_ARMED=false; submit_allowed=false. |
| 23 — Monetary SDK |0 attempts. Offline harness guarded16 methods;3 existing production-transport lock tests exercised. No private key, order, cancel, transaction or allowance operation. |
| 24 — Commit | Scoped local commit only; its exact SHA is supplied in the final response. This report is included in that commit. |
| 25 — Push | PUSH_PENDING_AUTHORIZATION. No push attempted in this mission. Explicit public-publication authorization remains absent following the prior automatic-review refusal. |
| 26 — Statistics | **24H_STATISTICAL_DESIGN_REQUIRES_SEPARATE_DECISION**. Criteria unchanged; incompatible old bootstrap minima still prevent a false economic PASS on12/6/6. This does not block technical capture. |
| 27 — Main verdict | **CAPTURE_24H_STORAGE_BLOCKED** |
| 28 — Historical replay command | Not applicable: source not qualified. No replay dataset manifest fabricated. |
| 29 — Capture command | Withheld: storage preflight fails. No command executed. |
| 30 — Storage-blocked action | Provide adequate storage before release of a capture command; do not restart historical-provider research. |

## Capacity evidence and limits

The established archive estimate remains21999279027 bytes; it was not remeasured. New instrumentation fixture measured 425.514 compressed framed bytes/state, 3539.699 bytes/opportunity for the tested one-level entry/exit case, and 223 bytes for a minimal checkpoint. An independent1000-record new-metadata write/fsync exercise used 284543 bytes in 0.094741s. Full raw depth is referenced, not copied per opportunity. See [overhead evidence](OBSERVATION_OVERHEAD.json).

These fixture averages are NOT upper bounds for arbitrary depth/event traffic. Therefore the final disk bound is enforced by byte quotas: RAW64GiB; book metadata16GiB; causal records8GiB; checkpoints256MiB; controls16MiB; recovery scratch1GiB; margin19169647002 bytes. RAW allowance is approximately3.12 times the previous archive projection. No claim is made that unknown future traffic fits24h: exceeding a quota stops the run and invalidates completeness. This distinction is explicit in the [final preflight](STORAGE_PREFLIGHT_FINAL.json). Real-time capacity of this new collector remains unproven; no duplicate smoke or production collector was run to imply otherwise.

The only fake-feed runtime exercises were short offline fixtures in temporary directories, with fake clocks/storage and no external connections. They are not a launched technical24h session. NTP/W32Time qualification will run only when a separately requested capture gets past the storage gate. A clean duration exit still requires subsequent admissibility audit and never sets readiness.

## Frozen identities

Transformed instrumentation AST SHA256: `1eef913e902a6ce31566e547e257ddfd0d507e8e8d644fd7521862e379781027`.
Combined source seal SHA256: `ce71b7d750ec18a01db79846dae6624403c5ce4157bf4879e98dfda8be78cf51`.

| Binding | SHA256 |
| --- | --- |
| analysis/run_d6_paper_live.py | `a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405` |
| analysis/d6/paper_live.py | `5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364` |
| analysis/d6/causal_capture_24h_v1/collector.py | `967b9abd60f0b9db158d336958d5574cc2bb873665dffe96853d6b6d96d360a1` |
| analysis/d6/causal_capture_24h_v1/runner.py | `f22315aec9f97d326083963857698c874b053bf95300425b04988a5f0c072358` |
| analysis/d6/prospective_24h_v1/PROTOCOL.json | `ae8dfbd188fe21537ec64c233af0780ce13e3fa0b4e88d984c3ee193f436dfb6` |
| analysis/d6/prospective_24h_v1/criteria.json | `e275857b535596aaecc33c842c3724ad855a3d3abe35c3414fd6a8ef9204d5c4` |

All runtime dependencies in the seal are listed in [SOURCE_HASHES.json](SOURCE_HASHES.json). No historical DB or timestamp was rewritten. The uncommitted telemetry and earlier harness-report changes were excluded from this mission.
