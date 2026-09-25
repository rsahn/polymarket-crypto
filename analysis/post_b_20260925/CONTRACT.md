# Post-B protocol v1 (scoped, fail-closed)

No offline proof authorizes readiness. ProductionReadinessCheck is not changed.

Qualify finalized separately: chain 137, finalized header B, latest header >= B, numeric re-read B with identical hash, second finalized header with nondecreasing height (same-height hash must match). This proves observed provider support, not independent consensus verification. Never substitute latest for finalized.

Verify Genesis and saved cursor hashes. Catch up only cursor+1..B, never from Genesis. Select H=latest ONCE after B. Scan every incoming CTF interval B+1..H with the identified TransferSingle/TransferBatch filters; verify known/discovered balances at H and hash(H). Nonzero inventory or unexplained incoming event => RECOVERY_REQUIRED. A cursor ahead of finalized B blocks rather than rewinding.

After preparation, acquire a NEW latest header witness W concurrently with the four account GETs. Require W.number=H and W.hash=hash(H), and re-read hash(B) in the same acquisition. If W.number>H, the interval H+1..W is NOT covered: bounded attempt ends POST_B_TAIL_ADVANCED, no automatic retry. A new head after the witness does not retroactively falsify the statement at W; it is outside its explicitly stated observation scope. Every use must check age <=500 ms from original request starts; sealing does not refresh any timestamp. Reorg(B/H), gaps, partial GET generation, future/stale observations => blocked.

current_inventory_proven means identified-CTF inventory at the canonical latest block observed at W, derived from the scoped Genesis plus complete forward intervals. It does not mean future/pending state or arbitrary protocols/global off-chain orders are known. A fresh witness validates an old scan only when it independently returns the exact same canonical scanned head; preserve scan_observed_ms separately. No provider event omission can be independently disproved by a single RPC: retain provider trust and Genesis coverage limitations.

The local probe collects public finalized/tail/WS evidence only; it loads no L2 credentials. Account generation remains a separately required input, not fabricated. Thus the probe never grants readiness or a complete account reconciliation. WS capture uses existing rejection rules; no tolerance or dropped regression. Capture is bounded and no real regression is claimed until observed.
