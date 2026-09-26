# POST_C_SOURCE_MATRIX

Audit before implementation, 2026-09-26. Result B, bounded to the inspected sources and installed polymarket-client 0.11.0. No claim that all possible future providers lack capabilities.

## Formal invariant

For wallet, chain, contract set and generation g, choose a causally consistent cut K=(W, CLOB sequence S, local ledger sequence L, indexer snapshot I if required). current_inventory_proven(g) requires: (1) authenticated scope-complete baseline C; (2) exhaustive relevant asset discovery and gap-free canonical chain coverage C+1..W; (3) all required balances at W/hash(W), rechecked; (4) complete authenticated orders, reservations, fills and settlement transitions through S, with a verifiable relation S<->W and no double-counted mined fills; (5) local ledger through L reconciled to that cut including fees and pending exposure; (6) any required indexer projection bound to the same cut, or a demonstrated redundant replacement; (7) every relevant mutation between cut and generation decision accounted for or a proven fence preventing it. No unexplained interval, unknown scope or missing page is permitted. A historical W alone is never proof at a later decision.

Transfers in/out, split/mint, merge/burn/redeem alter CTF balances. Settled fills alter CTF/collateral; matched but unsettled fills and open-order changes alter exposure/reservations offchain. Deposits/withdrawals/fees affect collateral. Indexer lag changes observability, not ownership. A timestamp is not a closed event sequence. These domains need a consistent causal cut, not identical request timestamps.

| SOURCE | DATA / KNOWN BOUNDARY | UNKNOWN BOUNDARY | BLOCK PINNING | COMPLETENESS |
|---|---|---|---|---|
| Polygon finalized/latest | Header number/hash, provider view | Later mutations, independent consensus | Numeric header yes | Header alone insufficient |
| CTF logs | Incoming TransferSingle/Batch, exact requested ranges | Unenumerated contracts/assets, outgoing event history, provider omission | Numeric ranges | Existing scoped coverage only |
| CTF balances | balanceOf for known/discovered IDs at scan end | Assets outside proven discovery universe | Numeric eth_call yes | Ending holdings of enumerated IDs; not pending fills |
| Collateral wallet | Contract balanceOf numeric block | Offchain reservations, later changes | Yes | Token balance at that block only |
| CLOB balance/allowance | balance, allowances | Processed block, account sequence and snapshot | No parameter in SDK builder | No common cut proof |
| CLOB orders | IDs, matched size, creation time, page cursor | Full wallet credential scope, atomic snapshot sequence | No | Drained pages != globally complete snapshot |
| CLOB trades | Trade IDs/status, tx hash, matched/updated time, cursor | Unreported matches, sequence high-water mark | No | Tx hash links individual settlement, not absent trades |
| Data API positions | current_size, last_event_at, opaque page cursor | Block/hash attached to each served page | No in installed spec | No cross-page/common-cut proof |
| Data API /v2/status | Public aggregate ingestion heights and serving lag | Binding to positions pages and CLOB state | No | Diagnostic capability EXISTS; not integrated |
| Local ledger / reconciliation | Genesis hash, local events and generations | Unseen external writes, remote completeness | Genesis yes; subsequent local sequence only | Local equality not source-completeness proof |
| Inventory checkpoints | Scoped canonical coverage through C, parent checksum | Post-C and unscoped inventory | C fixed | PASS_SCOPED_CATCHUP preserved |
| Generation timestamps | Local request/evaluation order | Remote snapshot/processed-watermark | No | Structural ordering only |

## Evidence provenance

LOCAL_CODE: backend/app/live/{ctf_inventory_probe,collateral_onchain,inventory_catchup,fixed_boundary,production_readonly,temporal_contract}.py; analysis/{qualify_post_b_proofs,qualify_post_genesis,run_inventory_catchup}.py. PublicRPC allows incoming transfer filters only. The scanner discovers IDs then queries their balances; it does not implement an outgoing/mint/burn event ledger. No permission to broaden its historic claims. PositionSource uses Data API to enumerate holdings and compares CLOB token balances, yet already returns complete=False. Removing positions is not presently justified: exhaustive global discovery and credential/ledger closure are missing.

SDK_CODE: account.py request builders accept filters/cursor, not block or snapshot; account models expose no common sequence. Trade transaction_hash is per row. Position has last_event_at, no processed block. parse_data_page validates has_more/cursor agreement but returns items/cursor only. list_positions_spec uses /v2/positions. No /v2/status integration found in its data action module or local facade.

OFFICIAL_DOC: [Data API v2](https://data-api.polymarket.com/v2/docs) documents /v2/status: background-cached snapshot, serving projection lag, aggregate ingestion cursors; dormant streams excluded. Positions pages have data/pagination, no block pin/snapshot parameter or page-bound watermark. Cursor binds query ordering/cohort, not a documented blockchain cut. last_event_at is a row event time. Therefore the finding is NOT "no watermark exists": it is NO_PROVEN_POSITIONS_PAGE_TO_INGESTION_TO_CLOB_BOUNDARY_BINDING. A future integration must establish those semantics first. (OpenAPI standalone fetch returned 403; embedded official JSON specification in /v2/docs successfully read.)

OFFICIAL_DOC: [Manage orders](https://docs.polymarket.com/trading/manage-orders) documents authenticated reads, cursors and credential/session-key scope restrictions. Its schemas do not document a common block or replay sequence. [User stream](https://docs.polymarket.com/trading/realtime-order-updates) has event timestamps, trade statuses and optional transaction hash, not a documented gap-free replay fence. [Settlement](https://docs.polymarket.com/trading/quickstart) explicitly separates match and asynchronous onchain settlement. [Positions](https://docs.polymarket.com/trading/positions/how-positions-work) explains token ownership and split/merge/redeem. [EIP-1898](https://eips.ethereum.org/EIPS/eip-1898) specifies blockHash/requireCanonical for state calls; local wrapper only allows numeric pinning, with hash rechecks. Support for EIP-1898 on the configured RPC was not experimentally tested.

EXPERIMENTAL_OBSERVATION: reference D6_INVENTORY_CATCHUP_20260926_182825_344562.json: C=94493874, 55533 blocks, 5554/5554 ranges, no failures, 112 checkpoints, through-C true/current false. Public GET /v2/status returned chain_id 137, min_synced_block 94495699, max_synced_block 94495700, computed_at 2026-09-26T18:51:31Z, age_seconds 23, serving lag_seconds 1. This is a service observation, not a wallet/common-cut attestation. No authenticated GET or monetary request was made for this audit.

## Decision and protocol

CURRENT_INVENTORY_PROOF_IMPOSSIBLE_WITH_CURRENT_SOURCES. W is constructible for scoped onchain state; NO sufficient common decision boundary is established. Missing: account scope-complete sequence/snapshot with a settlement linkage, positions-page binding to serving/ingestion state (if retained), and closure after W until decision. A nonzero latest height or 500/1300 ms changes none of these.

Retain scoped C and all sources. Emit current_inventory_proof with W/common/account boundaries null, explicit omitted interval after C through generation decision, and false execution flags. Do not implement a speculative positive verifier. Even synthetic "all covered" booleans or a fabricated common_watermark cannot grant true. Correct the legacy evaluate_post_b path which mislabeled a same-head witness as current inventory; retain original timestamps and scoped witness evidence.

Possible safe future designs: authoritative pinned CTF+collateral with proven complete asset universe; authenticated replayable account sequence and snapshot barrier; deterministic ledger covering all writers and settlements. Data API can be auxiliary only after proving every required decision input is replaced. Merely owning a local ledger does not exclude outside transfers or other authorized sessions.

## Worker audit

--watch exists, explicit poll interval required; serial catchup, lock, immutable checkpoints, fail closed, no authorization flags granted. Read-only process inventory on this host found no python run_inventory_catchup worker. No automatic service startup integration was found in the runner/wrapper. Bootstrap success is not permanent-worker liveness. No worker was started; a worker alone would not solve the common-cut blocker. No performance change.
