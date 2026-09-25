# D6 temporal critical path — 2026-09-25

Source: D6_POST_GENESIS_READINESS_20260925_155542_053884.json.
No target network request performed during this change.

## Measured budget, not projected performance

- Anchor checkpoint catch-up: cursor 94430390 -> finalized B 94431050,
  66 ranges. Already outside the final freshness generation. Never Genesis rewind.
- Minimal final tail: B+1=94431051 through fixed C=94431065, two ranges.
- Original scan start -> numerical C seal: 2961 ms.
- Four account GETs were ALREADY parallel: balance 259 ms, orders 263 ms,
  trades 259 ms, positions 299 ms. Seal -> all account completed: 301 ms.
- Account completion -> final evaluation: 460 ms, including sequential C/B
  rechecks, cursor persistence and local evaluation work.
- Total original scan start -> evaluation: 3722 ms.
- Last valid book source time -> evaluation: 1267 ms; receipt -> evaluation
  766 ms. This is age, not time spent sampling the book.

The old RPC log records starts only. Differences between adjacent starts include
request latency and dispatch/processing: they are NOT exact isolated RPC service
times. The approximately 0.5 second projected post-seal parallel budget is an
estimate, not an impossibility proof. No intrinsic >500ms minimum latency for a
source can honestly be established from this one run. New RPC records include
started_ms, finished_ms, elapsed_ms; the runner records scan, seal, account,
recheck and boundary evaluation phases. Readiness records final book sampling.

## Scheduling changes (fixed-C contract unchanged)

Reuse the validated cursor and qualified finalized B before final generation.
Choose C once. In the bounded CTF scan, request independent chain/header/code/log
reads concurrently (maximum eight workers), still with identical filters and
fixed block bounds. Decode all logs, discover actual IDs, then query their
balances concurrently at C. Only after those results, perform the existing
canonical recheck. Every partial/schema/chain/event failure remains fail-closed.
No proof is removed; no observed_ms is refreshed. An empty/no-op scan preserves
its old observation time and may remain stale.

Seal C numerically before starting the four parallel account GETs. After all
four finish, recheck C and B concurrently, by number, without querying latest.
PublicRPC now assigns a locked per-request ID and validates against that local
ID; the former shared counter check was unsafe for concurrent responses.

Run reconciliation and readiness immediately. Readiness samples the already
running WS last, after local checks and the transport-lock audit. No WS restart
or parser change. Persist the final cursor AFTER evaluation; report persistence
failure separately without changing Genesis or manufacturing readiness.

## Limits retained

500ms, fixed-C validator, Genesis, BTC V1, risk/sizing, monetary locks unchanged.
A >500ms source remains BLOCKED; concurrent requests do not waive completeness.
The distinct post-C current-inventory scope limitation from fixed-C is untouched.
This change makes no network PASS claim and does not guarantee the required
latency. The next manual run measures the actual parallel path before any further
latency conclusion. No retry loop and no head chase.

Command from repository root in target PowerShell:
python -B .\analysis\qualify_post_genesis.py --target-machine --health-contract
