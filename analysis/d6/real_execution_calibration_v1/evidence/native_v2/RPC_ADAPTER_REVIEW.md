# Offline acquisition freshness and concrete RPC adapter

2026-09-27. No account/private/RPC invocation, secrets, installation, config/flags/V1 change, order/signature or human receipt. Injected transports in tests are in-memory functions only. Actual RPC transport remains unauthorized pending explicit approval and parent QA.

## P2 completion-time freshness

bounded_acquisition.acquire no longer accepts caller now_ms. It samples its injected clock AFTER every provider has returned and evaluates original, unmodified observation timestamps at that completion time. Clock regression blocks. Provider exceptions and cancellation propagate without returning a bundle/verdict. Deadline and market_expiry_ms, when supplied, are checked at completion. A last provider advancing 6001 ms now yields CLOSING_OLDEST_READ_STALE, not bounded match.

## Concrete RPC implementation

bounded_rpc.BoundedRPC requires an explicit transport callable and exact HTTPS endpoint allowlist; no HTTP library/default endpoint/credential discovery exists. It restricts methods to chain ID, pinned blocks, allowlisted transaction receipts, bounded exchange code reads, and explicit contract/topic/block-range log queries. No send/sign/cancel/approval method exists. Endpoint userinfo/query/fragment, unbounded/latest ranges and foreign addresses/topics fail before transport.

Responses are typed and JSON-RPC ID/context checked. Calls have asyncio timeout plus wall/monotonic completion bounds, rejecting late cancellation-suppressing responses. Receipt attribution checks transaction/block/log consistency, removed flags, duplicate indices and a canonical block recheck. Log ranges are split into <=32-block chunks, total <=256 blocks, with pinned hashes for every block; reaching the response cap fails as possible truncation. All pages retain individual intervals and aggregate read start; canonical blocks are rechecked after reading. No unsupported pagination cursor is guessed. Empty/successful eth_getLogs output has coverage_proven=false: a provider can omit logs, so bounded query completion is not independent coverage proof.

provider(kind, reader) supplies an executable callback to acquire with the explicit adapter dependency. It does not self-issue authority envelopes: qualified readers supply original provenance; unproven canonical baseline/closing/coverage stay missing/UNKNOWN. Baseline token balance selectors/ABI composition are not invented by this narrow receipt/log/code adapter.

## Deployment proof boundary, not invented bytecode

The producer requires an independently authenticated **exact runtime artifact**, chain/address, pinned source commit, nonproxy designation and no unresolved immutables. It verifies chain 137, the block hash before and after eth_getCode, and byte-for-byte equality to expected runtime before emitting block-bound interpretation evidence. Nonempty code, a returned-code hash, source metadata or source commit alone cannot pass. Proxy layouts/unresolved immutables are unsupported. Fixture artifacts remain FIXTURE_ONLY.

Exact missing input: authenticated deployed-runtime bytes for each approved exchange address, linked to pinned source ccc0596074f4dfd62c944fbca4de252893b82b4b with reproducible compiler version/settings, linked libraries and constructor/immutable substitutions (or independently verified equivalent exact artifact). No such reliable runtime artifact was obtained. Public GitHub recursive-tree artifact discovery returned API 403 rate-limit; it was not retried or bypassed. This is not evidence that an artifact does not exist. No expected runtime hash has been invented and no real deployment is qualified.

## Native decoder limitation retained

native_v2.py does NOT independently decode FeeCharged. It uses the pinned OrderFilled per-order fee plus account collateral/ERC1155 transfer corroboration. Batched FeeCharged or transfer totals are never allocated heuristically. This is distinct from fee schedule/bound estimation and full-wallet qualification.

DRILL isolation remains unchanged; no operational instruction has been executed on behalf of the user. Parent independent QA precedes any human operational step.
