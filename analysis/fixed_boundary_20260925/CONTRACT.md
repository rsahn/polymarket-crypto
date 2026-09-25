# Fixed-C generation contract (2026-09-25)

Scope: D6 post-Genesis read-only qualification. No WS, Genesis, BTC V1,
risk, sizing or freshness-limit changes. No target-network run by Codex.

## Meaning and acquisition

G is a single invocation (no automatic retry). Its qualified finalized B is
provided by PASS_PROVIDER_FINALIZED_READ. The existing, Genesis-bound cursor
must not exceed B. A cursor ahead of B is blocked, never rewound.

Scan cursor+1..B, then select C from latest exactly once and record hash(C).
Scan B+1..C. Ranges must be contiguous, nonoverlapping and complete through C;
zero-length ranges are permitted only for equal endpoints. RPC errors or partial
results fail closed. These are provider-scoped proofs for the identified CTF,
not an independently verified proof of provider log completeness.

Read C by number and verify its identity/hash before starting account, orders,
trades and positions GETs. After all GETs complete, reread C and B by number.
A changed hash/identity invalidates the generation. Never read latest again to
chase C+1. Future blocks cannot retroactively change coverage through canonical C.

The scan's original acquisition start is retained as observed_ms. The seal is
separate metadata, NOT a refreshed inventory observation. Scan, seal, account
starts and final recheck must all remain within the unchanged 500 ms window at
evaluation. A slow scan therefore remains stale; this implementation does not
promise the target network can complete the generation in 500 ms. Subsequent
readiness evaluation applies its existing freshness gate again.

## Two distinct proofs

inventory_through_C_proven: identified-contract coverage through canonical C,
with no unexplained events or balances. This historical claim survives natural
head growth, but is not current state at a later account observation.

boundary_generation_complete: additionally, all four account sources belong to
G, began after sealing C and satisfy the real acquisition freshness window.

current_inventory_proven: remains FALSE with currently available sources.
Orders/trades are credential-view; positions are an indexer without a demonstrated
common completeness watermark. These reads do not exclude a conditional-token
transfer after C that is not yet indexed. Even empty responses and dedicated-wallet
intent cannot prove its absence. Events >C are outside the historical coverage
claim ONLY; they cannot be excluded from a future trade's inventory requirement.
A source-backed post-C completeness/decision watermark would be required to
close this gap. No local assumption supplies one.

Hence accepted fixed-C evidence reports POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN;
SYSTEM_READY remains false while this inventory gate is unresolved. The existing
MARKET_ELIGIBLE_NOW result remains independent. No offline evidence grants readiness.

Any discovered tail event or nonzero balance is RECOVERY_REQUIRED, even if its
net economic effect might be zero. Account activity or an unexplained collateral
change also requires recovery. It is never ignored or converted to FLAT. This
phase does not implement an activity projector or write to the Genesis ledger.

## Validation

Tests cover C+1/C+10, reorgs, gaps, overlaps, partial RPC, incomplete account,
500/501 ms, mixed generations, pre-seal account reads, CTF events, inconsistent
cursor bounds, numeric header identity, original scan timestamps and locked
readiness with a healthy WS. Historical head-witness pure tests remain legacy
coverage; the active --health-contract runner uses the fixed-C evaluator.

Manual command (existing configured RPC and DPAPI L2, no credential recovery):
python -B .\analysis\qualify_post_genesis.py --target-machine --health-contract

Expected output is a new D6_POST_GENESIS_READINESS_<UTC timestamp>.json.
It measures bounded evidence and remaining blockers; it cannot currently grant
current_inventory_proven or arm execution. No new run was performed by Codex.
