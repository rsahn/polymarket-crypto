# D6 forward genesis protocol

## Decision now
No actual genesis created. Available target reports demonstrate the beacon, pUSD balance and empty paginated credential/index views. No fresh CTF discovery result exists yet. No authoritative local ledger is configured. Absence of a ledger is not proof of no prior wallet history. Offline full readiness was executed, with actual saved observations retaining their original timestamps and unavailable adapters failing closed.

## Manual target execution
`python -B .\analysis\qualify_genesis.py --target-machine`
This command is authorized to create runtime/d6_genesis.db ONLY after all predicates pass. It never replaces an existing ledger; *.db is already ignored by Git. Report is a new GENESIS_READINESS_<UTC>.json. Full identifiers/snapshots stay in the local ledger; return only the redacted report.

Reads: fixed Polygon public RPC (chain, blocks, wallet code, official CTF incoming events and balances); CLOB /time, /balance-allowance type3, /data/orders, /data/trades; Data API /v2/positions; geoblock GET. Only JSON-RPC public read methods use POST, never CLOB. Existing DPAPI L2 only, loaded AFTER conditional discovery. No credential recovery, key, signature L1, secure client, deployment or transaction. Collateral metadata is reused from the already-qualified report; no decimals/symbol requalification.

Code-onset boundary: bounded binary search using historical eth_getCode for the confirmed beacon, verifies absent at previous block/present at boundary. Assumes code has not disappeared/reappeared. Does NOT claim no counterfactual transfers before deployment. RPC historical state failure => pending. A span >=50000 blocks refuses automatically; it requires a separately reviewed chunk manifest, not silent truncation. The CTF scan covers only the verified CTF contract and the index view, not every potential protocol.

Genesis snapshot: chain, block number/hash, timestamp, full beacon wallet, collateral contract/current raw/qualification digest, both-read-consistent paginated positions/orders/trades snapshots, every actually discovered conditional ID/raw balance, journal assets, explicit scope limits. Any nonempty unexplained view, conditional balance, changed view or prior recovery => RECOVERY_REQUIRED. Missing/stale/schema/archive evidence => GENESIS_PENDING. No invented token ID or FLAT.

Scope is D6_DEDICATED_FROM_GENESIS, based on the user's dedicated-wallet instruction. This accepts a reasonable scoped baseline, not proof of globally complete prior history, all API keys or all protocols. Other external/account activity remains a fail-closed operational limitation. A zero-holding CTF asset discovered in logs is retained with its provenance and zero balance, not discarded.

## Persistence and future activity
SQLite FULL synchronous, close, file fsync, same-filesystem atomic hard-link publication without replace. First row stores canonical snapshot and SHA256; explicit limitations participate in hash. Read validates genesis/hash and entire event hash chain. Event append uses BEGIN IMMEDIATE and optimistic last-hash check. Recorded types include INTENT/ACK/FILL/CANCEL_OBSERVATION/SETTLEMENT/RECONCILIATION/RECOVERY_REQUIRED. Recovery is sticky and blocks new INTENT. Baseline reconciliation refuses missing/freshness/scope/identity/holdings/order/cash mismatch; records RECOVERY_REQUIRED.

The journal API is implemented and tested. Monetary runner is still disconnected. Any future execution integration MUST journal intent durably before submission, observations after response, and reconcile new activity from genesis anchor before decisions. It must use this ledger as authoritative, not a second independent store. This connection is not claimed implemented or enabled: future_execution_binding_ready=false remains explicit. No real activity can be initiated by these tools.

## Full readiness
All 12 gates are evaluated through ProductionReadinessCheck, including account, positions, actual disconnected BookStateSource, geoblock source and session risk. Parallel source reads avoid artificial sequential aging; timestamps are not rewritten. pUSD checks use qualified collateral units, not USDC aliases. Genesis integrity alone does not satisfy recovery; reconciled_now must be explicit and current. A new accepted genesis defines session PnL=0 at its boundary, not lifetime wallet PnL. Without accepted genesis session risk stays unavailable. BTC V1 is not changed and no synthetic book stream is installed.

Offline result: only transport_lock and live_flags_disabled pass; remaining gates are stale/unavailable, including account authentication freshness and balance/allowance freshness. This does NOT invalidate collateral identity already qualified. Target command reevaluates available network sources; a disconnected book and the future journal/runner binding remain real pre-execution work.

Validation: 15 new tests; maximum project suite 495 passed, 25 subtests passed, 0 failed/errors, 3 warnings. Atomic Windows defect preserved in ATOMIC_RED.log and fixed in ATOMIC_GREEN.log. Static audit AUDIT_OK; 16 SDK monetary methods guarded; zero SDK monetary attempts. No actual ledger exists at runtime/d6_genesis.db at completion. No authenticated or RPC network call was executed during development.
