# Concrete offline HTTP assembly and deadline repair

Entry point: **rpc_assembly.assemble(...)**. No CLI activation, credentials, default endpoint, scheduler or import-time I/O. Caller explicitly supplies approved endpoint identity, transaction/block allowlists, deadline/call budget, independent evidence and trust pins. Tests replace HTTPSConnection with in-memory HTTP fixtures; no real RPC/account calls occurred.

## Delivered

bounded_acquisition validates deadline and market expiry before first and EACH subsequent callback, passes remaining_budget_ms, awaits async providers within remaining budget, and retains completion-time clock/expiry checks. Monotonic total budget rejects late cooperative completion. Expired-start zero calls; crossing-midway no later callbacks. Cancellation propagates and async tasks remain owned. Arbitrary synchronous callbacks cannot be forcibly interrupted: they must obey their supplied budget; late results fail closed. Cancellation-suppressing callbacks delay return rather than becoming abandoned tasks. No retries.

rpc_assembly connects standard-library HTTPS POST -> BoundedRPC method/address/topic/tx/block validation -> canonical receipt/log/code observations -> timestamped observation envelopes -> native decoder verification -> acquire -> existing bounded validator. Status redirects, altered endpoint paths, invalid JSON/duplicate fields, response sizes, socket read budgets and cumulative call/deadline exhaustion block. It follows no redirects, adds no Authorization and does not discover credentials. Socket thread cancellation is cooperative: ownership is retained until socket operation ends, never advertised as forced interruption. DNS/OS/network operations can delay cancellation; this is not a hard real-time kill guarantee. Actual approval must accept this limitation or require a separately reviewed process-isolated transport.

The complete mocked composition performs receipt+recheck and fixture code+chain+before/after block checks, invokes native validation and reaches acquisition qualification. Generated envelopes are observations, not self-authenticated proofs; independent authority rejection is exercised. Coverage logs never synthesize completeness.

RuntimeArtifactVerifier checks independently configured origin->manifest digest trust pins, exact source contents/digests, compiler/build fields, runtime digest, pinned commit and nonproxy/immutable restrictions. There are NO built-in production trust pins. Hashing an arbitrary manifest itself does not make it trusted. Synthetic fixture pins remain synthetic. Trusted-origin provenance is an operator/reviewer input, not a callback boolean that can supply a missing artifact.

## Precise remaining software / evidence

- This is a concrete receipt/log/code composition, NOT a complete automatic source of baseline cash/asset balance snapshots, terminal CLOB observations, finality or independent event coverage. Those original qualified envelopes/correlation records remain explicit inputs. Concrete baseline eth_call selector/readers and independent finality/coverage producers are not implemented by this pass.
- Real runtime build artifact remains absent: per-address exact deployed bytes plus verified origin, commit, compiler/settings, dependencies/libraries and constructor immutable substitutions. No source-only claim or expected hash invented. forge and solc were not found by Get-Command; no build/install attempted. Prior public API rate limit respected with no retries.
- Compiler/build-manifest validation is integrity/trust-pin validation, not a reproducible compiler run or independent proof that source compiles to runtime. Proxies/unresolved immutables remain unsupported.
- No live applicable fee bound, full-wallet completeness, operator attendance, real drill or human receipt established. FeeCharged is not independently decoded.

## Future minimal authorization request template — NOT AUTHORIZATION

Only after parent QA and genuine artifact/evidence availability, request:
1. One explicit nonsecret HTTPS endpoint identity (host/path, no userinfo/query/credentials), no redirects.
2. Polygon chain 137; methods only eth_chainId, eth_getBlockByNumber(false), eth_getTransactionReceipt, eth_getLogs and eth_getCode; NO eth_call unless separately justified/approved.
3. Explicit transaction hashes and block number->canonical hash map, max 256 distinct blocks; no latest/unbounded ranges.
4. Explicit exchange address selected from documented E111/e222, pUSD C011 and CTF 4D97; exact topics OrderFilled/OrdersMatched/ERC20 Transfer/ERC1155 TransferSingle/TransferBatch for requested reads.
5. One finite approval window, total max_calls computed for those requests (<=256), per-socket/call <=2s, log chunks <=32 blocks, <500 logs/page, <=1MiB HTTP responses, no retries. Specify concrete deadline and market expiry before invocation.
6. No signatures, trades, cancellations, allowance/funding changes, credentials/config/flags or human custody receipt.

Empty allowlists or absent approval mean no invocation. No actual request is made by this document.

Final validation: inspected bounded suite **565 passed in 16.46s**; focused assembly **9 passed in 2.21s**, nonadditive. Diff whitespace check no error apart from pre-existing unrelated CRLF warning. No whole-repository/live qualification claim.
