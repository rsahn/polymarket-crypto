# Final bounded offline delivery; stop at real proof gaps

No account/RPC/credential/live call, install/build/service, flags/config/V1/cap change, monetary operation or human receipt. All HTTP fixtures use in-memory connection factories. Existing source and previous work retained.

## Software

Effective assembly deadline is min(request deadline, market expiry). HTTPS and RPC layers share absolute wall deadlines plus monotonic lifetime budgets checked before EVERY request. Expiry during receipt canonical recheck stops before any deployment chain/block/code/block calls. Earlier per-provider and post-acquisition checks remain.

Concrete entry remains rpc_assembly.assemble(...), now accepts reader_plan={baseline_block,closing_block} and provider_identity. concrete_readers.ConcreteReaders wires pinned pUSD balanceOf(address), ERC1155 balanceOf(address,uint256), before/after canonical block checks, raw-read intervals, terminal normalization, finality claim canonical recheck and coverage/log/receipt reconciliation into the assembly. ETH_CALL is allowed only for exact generated address/selector/account/token/block parameter tuples, no arbitrary calldata. Mapping accepts explicit D6 identity and one/two declared positive uint256 token IDs; existing market/asset mapping records and bounded validators remain required.

Terminal and finalized/coverage facts originate in supplied raw observations/claims, not fabricated HTTP endpoints. Finality/coverage source envelopes require independent verification before reading; output envelopes require independent verification too. PinnedEvidenceAuthority supplies a concrete provider-identity + independently configured exact evidence-digest trust boundary, with fixture distinction and payload verification. No default trusted provider/pins or boolean-derived global completeness exists. This is intentionally reviewed-evidence trust, not a new automated consensus service.

Receipt/log/code HTTP composition plus these readers and native validation are implemented. Snapshot->native receipt->closing->bounded conditional verdict is tested with explicit fixture authority. Full HTTP assembly tests test refusal without authenticated runtime/evidence rather than manufacturing live trust. OrderFilled per-order fees plus transfer corroboration remain supported; no independent FeeCharged allocation/decoder.

## Lifecycle limits

HTTP response sizes, duplicate/malformed JSON, nonempty log queries, foreign/reorg/truncated responses and cancellation lifecycle are covered. Socket thread work remains owned through closure after cancellation. No forced DNS/OS termination guarantee; synchronous or cancellation-suppressing work can delay caller return. This is not an unattended/production-ready launcher.

## Genuine remaining inputs; no further expansion

1. Independently authenticated per-deployed-address exact runtime artifact, linked pinned commit/compiler/settings/dependencies/libraries/constructor immutable substitutions. No artifact or hash fabricated; no forge/solc/build/install attempted this pass.
2. Approved provider identity/trust pins and actual raw block-pinned observations, qualified finality/coverage claims, terminal observations and attribution. Exact reviewed evidence trust is implemented, but no real authority enrollment or remote finality/completeness proof exists.
3. Actual operator attendance and no-money DRILL, then separate genuine consent/launch review. No receipt or attendance asserted.
4. Real use of RPC methods including newly implemented eth_call remains UNAPPROVED.

## Minimal future authorization specification (unexecuted)

One explicit nonsecret HTTPS endpoint host/path, no redirects/credential discovery; Polygon 137; exact block-number/hash and transaction allowlists; selected documented exchange, pUSD C011 and CTF 4D97 addresses. Methods eth_chainId, pinned eth_getBlockByNumber(false), eth_getTransactionReceipt, eth_getLogs, eth_getCode, plus separately approved exact eth_call calldata for pUSD 70a08231 and CTF 00fdd58e with D6 and declared tokens at baseline/closing blocks only. <=256 total calls/blocks, <=32 blocks/log chunk, <500 logs/page, <=1MiB bodies, <=2s socket/call and explicit total deadline/market expiry; no retries. Actual numeric block/tx/token lists and deadline must be provided before approval/use. This document grants nothing and makes no request.

CALIBRATION_BLOCKED. Parent final targeted QA before user operational instructions.

Validation: **577 passed in 16.93s** inspected bounded suite. Whitespace check exit 0, only pre-existing unrelated CRLF warning. No whole-repository/live PASS claim.
