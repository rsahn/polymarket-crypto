# BTC V1 initial qualification 24h

**BTC_V1_24H_PROTOCOL_BLOCKED** — preparation complete; no economic experiment started.

The user's duration decision precedes new economic access. It creates a separate version, not a change selected from results. No new TRAIN/VALIDATION/OOS, PAPER or micro-live was opened. No capture launched. No real T0 selected.

## 1–3. Version and preservation

- Protocol: BTC_V1_24H_INITIAL_QUALIFICATION_V1, SHA256 `ae8dfbd188fe21537ec64c233af0780ce13e3fa0b4e88d984c3ee193f436dfb6`.
- Criteria: BTC_V1_FIXED25_24H_CRITERIA_V1, SHA256 `e275857b535596aaecc33c842c3724ad855a3d3abe35c3414fd6a8ef9204d5c4`.
- 12h TRAIN / 6h VALIDATION / 6h unique OOS; FIXED25; BTC UP/DOWN 5m; embargo 60s; whole-market purge unchanged.
- PURPOSE=INITIAL_MICROLIVE_QUALIFICATION; NOT_LONG_HORIZON_STABILITY_PROOF=true.
- Old 72/48/48 version preserved **YES**, including old criteria hash `869a386b9112a572247e3fb61ffbf4a27afb20493a791929e72f52bc0d9cd06a`.

The only old criterion changes are duration_hours and version. A rationale is added. Gross/net profitability, drawdown, fill/opportunity/market minima, confidence method, seed, sensitivity and coverage thresholds are unchanged. Eight active 6h blocks cannot fit in any split (maxima 2/1/1). The 12h sensitivity block needs at least 24h under the existing bootstrap implementation; 6h validation/OOS cannot even meet its 12h primary minimum. All splits therefore have a prespecified **INCONCLUSIVE_INSUFFICIENT_SAMPLE** outcome until a separately justified, versioned statistical design is authorized. This is not an economic result and is not silently relaxed.

`preparation/MANIFEST.json` and `PREPARATION_SEAL.json` freeze protocol, criteria, preparation code, existing strategy and ledger source hashes. Manifest SHA256 `4339d6948f91c40297c3bd7a08b7cc3016ee1bdaf1915f528f2f6090c2b99117`. The future economic runner hash, source/collector identities, fee/depth policies, T0 and actual boundaries remain null. No real loader is enabled. Exclusive writes and seal verification reject replacement or mutation. Once admissible data exists, any experiment needs a new complete immutable manifest before access, bound to exact source bytes and identities. Relative boundaries are 0/12/18/24h; the 60s embargo removes markets/features that touch excluded time, without moving boundaries or inventing observations. Existing AccessGate first-access mechanism is reused unchanged; its synthetic regression tests do not open any real source partition.

## 4–5. Local data audit

Identified Binance collection: `data/poly_quant.db`, table `btc_ticks`, source binance / btcusdt. Dataset SHA256 `01018d9a00b1c53c7789708ae514372d0240209c38cbd37f7bf402da10940c16`. File size 1,056,837,632 bytes, no WAL. Schema and all gap intervals are preserved in `LOCAL_DATA_AUDIT.json`; source bytes and modification time remained unchanged.

Receive span: **2026-09-18 08:55:42.644 UTC → 2026-09-19 23:50:37.603 UTC**, 38.915266 h, **1,092,904 ticks**. Stored fields: local ID, source/symbol, source event and receive ms, trade price, optional bid/ask quantities. Collector code indicates aggTrade price with cached bookTicker top. Original raw messages, aggregate trade IDs, generation and inter-feed sequence are not stored in this schema. This source is therefore not a complete websocket replay.

Sorting receive timestamps still reveals **134 gaps >5s**, maximum **3,101,299 ms (51m41.299s)**; longest segment under that already generous diagnostic threshold: **2.292194h**. ID order contains 2,079 receive-clock regressions. Gaps are observed silence, not proof of packet loss; neither raw sequence continuity nor clock quality is established. The 5s diagnostic is not a newly relaxed admissibility threshold for a 250ms signal. The claimed continuous admissible 24h collection is **not demonstrated**.

The exact comparison window is the first Binance receive timestamp plus 24h: **2026-09-18 08:55:42.644 → 2026-09-19 08:55:42.644 UTC**. This is an audit window, not experiment T0, and was chosen without returns. It contains:

| SOURCE | START UTC | END UTC | EVENT_COUNT | GAPS | TIMESTAMP_RESOLUTION | DEPTH_AVAILABLE | BOOK_IDENTITY_AVAILABLE | CAUSAL_REPLAY_CAPABLE |
|---|---|---|---:|---|---|---|---|---|
| poly_quant.db / btc_ticks | Sep18 08:55:42.644 | Sep19 08:55:42.589 | 779,694 | Explicit gap list in matrix | 1ms stored | No | No | No |
| poly_quant.db / poly_quotes, both durations | Sep18 10:17:56.117 | Sep19 08:55:42.631 | 4,128,088 | Global and per-duration diagnostics; token continuity unproven | 1ms stored | Top only | No | No |
| poly_quotes / 5m | Sep18 10:17:56.127 | Sep19 08:55:42.631 | 1,966,702 | See exact per-duration matrix | 1ms stored | Top only | No | No |
| poly_quotes / 15m | Sep18 10:17:56.117 | Sep19 08:55:42.604 | 2,161,386 | See exact per-duration matrix | 1ms stored | Top only | No | No |

5m quotes contain 520 distinct tokens, but market_id is only `5m`, not a unique slug/condition/generation. There are source/receive ms, local IDs, token and outcome, bid/ask/top quantities; no full levels, raw price_change, actual decision book selection or rotation event identity. Token changes do not repair missing generation/market metadata.

`LOCAL_24H_DATA_MATRIX.json` includes all inventoried data/ DB ranges: the D5/D51/D6 full-depth captures begin September20 or later, outside this exact window. WAL-bearing sources were inspected with immutable main-file reads only and explicitly marked incomplete; no checkpoint/WAL modification was performed. `LOCAL_DERIVED_INVENTORY.json`: the root Bonereaper snapshot is benchmark activity; C3 snapshot contains derived shadow observations. D6 Parquet manifests point to the September20 short-window source and disclose omission of BOOK.payload_json; they cannot supply this September18 window or missing original decisions. Technical benchmark DBs and derived reports do not create independent raw provenance. This inventory is scoped to the authorized repository, not a claim about other disks/providers.

## 6–8. Historical sources and reconstruction

See `EXTERNAL_SOURCES.md`, with primary-source links, classification, dates, clocks, retention/access/cost limits and bounded request evidence. Official Polymarket current books, price histories and Polygon settlement logs do not provide the required historical off-chain depth plus local selection. Binance minimal exact-date REST request succeeds (three aggregate trades); original local arrival clocks remain absent. PMXT v2 is a plausible full-depth candidate, but September18/22 objects returned 404 and its April17 example returned 403. Reconstruction result **RECONSTRUCTION_BLOCKED_NO_ACCESSIBLE_BOOK_SAMPLE**; book/top/depth/order match, time difference and missing-event counts remain UNKNOWN.

**E — DATA_SOURCE_QUALIFICATION_INCOMPLETE.** Local data is LOCAL_24H_CAUSAL_DATA_INSUFFICIENT. A/B/C have no causal reconstruction proof. D is not asserted while an external candidate remains inaccessible/unqualified. No PnL was used to classify sources or depth semantics.

## 9–11. Depth, binding and fees

- DEPTH_MODEL_NOT_IDENTIFIABLE_FROM_CURRENT_EVIDENCE: previous 15 opportunities still have zero identifiable actual entry states; nominal signal+250ms cannot repair them. Models A/B/C are not selected.
- REAL_V1_BINDING_NOT_QUALIFIED: R1 remains unadopted. `OBSERVABILITY_CONTRACT.md` specifies missing signal, entry/exit selected state/depth, all clocks/order, simulated fills/residual and fee links. No economic logic changed.
- MARKET_FEE_UNQUALIFIED: existing evidence does not establish an applicable authoritative actual charge for hypothetical fills, exact per-fill rounding/allocation, or a proven aggregation-independent upper bound. Builder fee fields do not prove venue taker charges. No new account request; no fee=0 fallback. Existing fee evidence and counterexample preserved.

## 12–19. Capacity, solely for 24h

| Field | Value |
|---|---:|
| ARCHIVE_24H_BYTES | 21999279027 |
| JOURNAL_24H_BOUND | UNKNOWN |
| CHECKPOINT_24H_BOUND | UNKNOWN |
| SCRATCH_REQUIREMENT | UNKNOWN |
| ENGINEERING_MARGIN | UNKNOWN amount; 20% of all qualified components, rounded up |
| QUALIFIED_24H_REQUIRED_SPACE | UNKNOWN |
| CURRENT_FREE_SPACE | 45748113408 bytes at measurement |
| ADDITIONAL_SPACE_REQUIRED | UNKNOWN |

Archive arithmetic: ceil(254621.285030 × 86400) = 21,999,279,027. This is a projection from the existing lossless capture, not a hard future traffic bound. Even though the archive projection alone fits current free space, unknown journal/checkpoint/scratch cannot count as zero. **STORAGE_24H_UNQUALIFIED**.

**REPLAY_24H_UNQUALIFIED**. Existing synthetic measurements reused: 100,000 MARKs /24.131s /34,668,544 peak bytes, and 60,000 book-related events /27.088s /34,672,640 peak bytes. No probe repeated. They do not bound the actual 24h event mix, max record/depth, active positions, history-scanning runtime or scratch. Restart into new scratch is tested; no production checkpoint protocol is qualified. Longer-horizon storage is not a readiness criterion for this phase.

## 20–29. Verification and delivery

- Targeted: **10 PASS**. Full suite: **1011 PASS, 98 subtests, 0 FAIL**; 3 existing DuckDB deprecation warnings. Evidence: FULL_SUITE.log and VALIDATION.json.
- Audit: **PASS**, 113 protected prior files identical; preexisting tracked modifications preserved. Leak scan PASS (scoped credential/PEM/token checks, no credential files added).
- BTC V1 hashes unchanged: paper_live.py `5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364`; run_d6_paper_live.py `a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405`.
- D6 inventory/Genesis/post-C/WS/risk/readiness/semantic components untouched. SYSTEM_READY=false; current_inventory_proven=false. Historical D5 remains FAIL.
- REAL_ORDERS_ENABLED=false; LIVE_EXECUTION_ARMED=false; submit_allowed=false. Monetary SDK attempts **0**, 16 methods guarded; external test connections **0**. Public historical HTTP GET probes only outside the test harness.
- Commit: scoped local commit after final audit; exact SHA supplied in delivery message and recoverable with `git log -1 -- analysis/d6/prospective_24h_v1`. Existing unrelated modifications excluded.
- Push: **PUSH_PENDING_AUTHORIZATION**. Prior automatic approval review rejected public publication of code/internal evidence without payload-specific authorization; no new push attempted.
- Exact verdict: **BTC_V1_24H_PROTOCOL_BLOCKED**.

## 30–31. Conditional commands

Not applicable under source verdict E. Neither a qualified capture runner (D) nor sufficient historical data (A/B/C) was established. Supplying a start/replay command would falsely imply readiness. Preparation tooling is deliberately not an economic dataset loader. No automatic OOS access or experiment is scheduled by this work.
