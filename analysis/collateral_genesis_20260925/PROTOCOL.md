# Collateral and initial inventory qualification

## Run on target machine
`python -B .\analysis\qualify_collateral_inventory.py --target-machine`
Return only the timestamped COLLATERAL_INVENTORY_READ_ONLY_*.json. It contains the phase-scoped ProductionReadinessCheck, not a claim that all live gates were reevaluated. No previous report is overwritten.

The RPC is https://polygon.drpc.org, pinned from SDK 0.11.0 and official Polygon https://docs.polygon.technology/pos/reference/rpc-endpoints. HTTP POST transports JSON-RPC reads ONLY to that exact public RPC; CLOB stays GET-only. No generic arbitrary call, signature, transaction, approval or secure client. Redirects rejected, no provider fallback. Single-provider observations are not independently verified consensus proofs.

Contract 0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB comes from SDK and https://docs.polymarket.com/resources/contracts. https://docs.polymarket.com/concepts/pusd documents pUSD, ERC20 and 6 decimals. Probe verifies chain 137, recent fixed block, nonempty code at token and confirmed beacon, canonical ABI decimals()/symbol(), balanceOf(beacon), unchanged block hash. Metadata mismatch or RPC error blocks conversion. Two fresh type3 COLLATERAL CLOB reads bracket the RPC observation; both must equal the positive on-chain balance. The mapping is documented SDK/protocol identity plus numerical corroboration, not a cryptographic CLOB attestation. Only after that evidence is available does the NEW raw reading receive a pUSD denomination (exact Decimal arithmetic). No historical number is converted in this implementation run.

## Initial state and GENESIS_RECONCILED contract
The qualification reads paginated current index positions and credential-view orders/trades. It reads an explicitly configured READONLY_EXECUTION_STATE_DB using SQLite mode=ro/query_only. Asset IDs are taken from actual execution_events/value/order/token_id and the snapshot, not invented from a market list. No configured ledger is NOT evidence no session existed. Evidence reports persist independently; no execution DB is created or altered.

Current state is GENESIS_RECONCILIATION_PENDING. To establish GENESIS_RECONCILED later:
1. Establish the authoritative ledger location and signer/beacon/chain identity; inventory all prior D6 session journals, with hashes and import boundaries. An explicit no-prior-live-session attestation must be supported by deployment/run provenance; absent file is insufficient.
2. Freeze a start block/hash/time, declare supported asset protocols/contracts and discover all relevant IDs from deployment onward, including external deposits. Read balances for their union with journal and index IDs; settle any nonzero or unknown position and reconcile pending lifecycle states. Do not mark an open holding CLOSED.
3. Establish order coverage beyond a single credential (account-wide capability or explicit exclusive-account control policy with continuous external-activity detection); preserve all evidence and coverage limitations.
4. Record a genesis event with evidence digests, covered blocks, credential scope, actual initial holdings, unsettled orders and initial session-risk accounting. GENESIS_RECONCILED is a scoped evidence status, NOT an alias for CLOSED/FLAT; a future controller integration must explicitly handle it. Current ExecutionController is not changed to accept this new state. Missing scope/continuity => remain pending.
5. Persist into a dedicated new ledger only after these checks; never overwrite old DBs. Subsequent startup requires fresh reconciliation, not trust in the genesis label.

Zero positions means no rows in the queried index/filter at that instant, not no other/archived protocol holdings. Zero open orders and zero trades mean empty current credential views with pagination complete; not account-global coverage, all historical fills or externally transferred inventory. These are not active API failures and are reported as passing scoped observations, while the coverage blocker remains.

## Separate CTF probe
analysis/qualify_ctf_inventory.py --from-block <verified-start> --to-block <fixed-end> reads public Polygon only. Requires explicit block range (maximum 50000 blocks per run), 500-block chunks, official Conditional Tokens 0x4D97DCd97eC945f40cF65F87097ACe5EA0476045, ERC1155 TransferSingle/TransferBatch incoming events and balanceOf(address,uint256) at end block. Newly found IDs outside local journal are counted as discoveries; no IDs/account addresses in output. It verifies code, chain and unchanged anchor. No credential is loaded. Source contract: official contracts documentation; ERC1155 ABI standard https://eips.ethereum.org/EIPS/eip-1155.

No deployment block is guessed. The tool cannot prove an archive provider returned every log or cover all other token protocols; complete=false always. Multiple partial runs require a separately reviewed no-gap coverage manifest before a global inventory claim. CTF alone does not establish PositionManager/combos or other ERC1155 contracts coverage. No scan has been executed here.

## Remaining blockers
Collateral chain/account mapping observation pending target run. Inventory discovery/coverage, authoritative session history and genesis reconciliation remain unproven. Confirmed beacon, type3 historical equality and successful positions endpoint are not reopened. Live flags false, BTC V1 unchanged, monetary transport locked. Full live readiness also needs fresh book/geoblock/risk checks at its own boundary; this two-blocker report does not silently mark those checks passed.

Validation: 16 new fixture tests; maximum project suite 480 passed, 25 subtests passed, zero failed/errors, 3 warnings. Static AUDIT_OK. OFFLINE_PROOF: SDK monetary attempts 0, 16 guarded methods, both flags false. No target RPC, authenticated GET, private key or credential read executed during development. BTC V1 and previous comparative report unchanged.
