# Reuse the scan's final canonical witness (2026-09-25)

Baseline: D6_POST_GENESIS_READINESS_20260925_164926_334174.json.
Budget from inventory acquisition: scan 147 ms (including its final numeric C check), redundant seal 69 ms, account 221 ms, final B/C checks 71 ms, remaining reconciliation/sample/evaluation 8 ms = 516 ms. Account age = 300 ms.

Change: scan_ctf captures the actual start/receipt and header of its final numeric C read, after all logs and balance calls. fixed_scan forwards that witness for this scan only. seal_tail validates the complete header against the chosen C and the acquisition-time ordering, then reuses it instead of issuing an immediate second numeric read. No timestamp changes. An empty tail discards old witness metadata and retains an explicit fresh numeric seal; old inventory acquisition time remains old. Missing proof uses the original explicit read. Malformed/reorg proof blocks. Post-account canonical B/C rechecks remain required and parallel with each other, not with account: otherwise a reorg during account could be missed.

Before DAG: scan including final C -> repeat C -> account group -> final B/C -> reconcile/sample/evaluate.
After DAG: scan including final C used as seal -> account group -> final B/C -> reconcile/sample/evaluate.
No verification property removed. Fixed-C contract evaluator unchanged. No disk writes moved; checkpoint still follows evaluation. Ledger reads retained for change detection.

Illustration ONLY with every other baseline duration held constant: 516-69=447 ms inventory age. This is not a measured AFTER result or a latency guarantee. Account age would remain 300 ms under that assumption. New report final_timing_budget provides actual inventory/account/book ages and critical-path wall duration. Original scan start is preserved. Current inventory is not established merely by faster acquisition; post-C scope remains unproven and fail-closed.

Pool reuse: baseline proves warm RPC connections, but first CLOB/Data account requests each establish TCP/TLS. No speculative private HTTPX preconnect APIs introduced. No account data preloaded. This phase uses the demonstrated redundant RPC instead, without new routes or authenticated warmup traffic.

WS conclusion: official https://docs.polymarket.com/market-data/realtime-data exposes book and price_change timestamps and optional hashes, but no sequence-based snapshot coverage certificate or guarantee that an earlier timestamp necessarily means included in that snapshot was found. Installed polymarket 0.11.0 market_protocol.py routes/parses events; inspected code does not establish that guarantee either. Three observations prove receive/source order differ, not snapshot coverage. Tests now explicitly cover -2, -15, -16 ms; all remain PRE_SNAPSHOT_DELTA_SUPERSESSION_UNPROVEN and BOOK_REGRESSION. No semantic WS change or second WS commit.

Missing evidence: a provider contract tying snapshot coverage to delta sequence/watermark (and generation), or independently verifiable canonical state with a documented checksum/sequence reconciliation algorithm. A safe future architecture quarantines ambiguous deltas, invalidates decision eligibility, obtains a new authoritative snapshot and validates continuity before resuming. A timestamp magnitude threshold or mere repeat observations cannot supply that evidence. No automatic resubscription/reconnect is added here.

Validation: RED reproduced missing witness and missing reusable seal; GREEN targeted success, then complete offline suite. Existing boundary 500/501 tests and fixed-C negative cases remain active. Audit and scoped pattern leak scan included separately. No target run executed, no secrets loaded. Genesis/BTC V1/risk/sizing/500ms unchanged. Flags false, no monetary calls.
