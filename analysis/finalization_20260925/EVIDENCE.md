# D6 finalization checkpoint — not live-ready

## Delivered and validated
- Explicit task-scoped 1300ms policy shared by account/position readers, book stream, readiness, fixed-C generation, controller and exit planning. Historical default remains 500ms; no timestamp is changed. CLI: --freshness-ms 1300. Independent asyncio tasks and thread workers tested.
- ExecutionStateSources now carries a detached exit book and explicit slippage source; no optimistic slippage default.
- Restart can reconcile a known terminal cycle after failure of the last account read. Both order legs, filled amounts, token identity and explicit flat account evidence are required. No order retry, cancel or submit occurs in recovery. Unknown IDs, missing asset, live order, residual inventory or inaccessible remote state remain blocked.

## Validation
Policy RED: missing policy module (new feature). Recovery/source RED: 3 reproduced failures, 33 passed. Final full guarded suite: 685 passed, 8 subtests passed, 3 deprecation warnings. Policy focused: 13 passed. Audit passed, transport hard locked. SDK monetary attempts = 0. Pattern leak scan is scoped to changed source and evidence, not a global absence proof.

## Four requested workstreams
1. Inventory: BLOCKED under the retained current_inventory contract. Fixed-C is unchanged except the authorized freshness policy. An empty indexer and credential-view order/trade snapshots do not rule out an unseen post-C conditional-token transfer. test_inventory_information_gap.py records this indistinguishable-observations counterexample; it is a logical counterexample, not a new network observation.
2. 1300ms: IMPLEMENTED AND OFFLINE TESTED; explicitly selected in the manual qualification CLI. 1301ms and future timestamps rejected.
3. Real runner: PARTIAL. Exit sources and conservative restart recovery are connected/tested with fakes. No production-complete account source or authoritative post-trade Genesis projection has been established; monetary adapter remains locked. It would be incorrect to call this a finished live integration.
4. Validation: OFFLINE COMPLETE FOR THIS CHANGE; target network not run. POLYGON_ARCHIVE_RPC_URL is absent in this process (presence check only); the user's separate PowerShell environment is not inherited. No credentials, private key or authenticated network were used.

## Missing external contract
Inspected SDK 0.11.0 signatures are in SOURCE_CAPABILITIES.json. The inspected account methods have no common block-bound parameter. Official user stream documentation describes authenticated order and trade events; the reviewed schemas do not document a shared CTF/indexer completeness watermark: https://docs.polymarket.com/trading/realtime-order-updates . This is a limit of the inspected sources, not a claim that no provider can ever supply one.
A provider-backed common completeness boundary (including conditional transfers) or an explicitly revised decision-scope contract is needed before current_inventory can become true. No such proof was invented. Additional permissions and larger freshness thresholds cannot create it.

## Manual qualification only
From repository root, in the target PowerShell where the existing read-only RPC is configured:

    python -B .\analysis\qualify_post_genesis.py --target-machine --health-contract --freshness-ms 1300

This command is read-only, not a live launcher, and does not resolve the post-C scope gap by itself. Do not change flags to force it through. Report filenames remain timestamped and non-overwriting. No new qualification was started automatically.
