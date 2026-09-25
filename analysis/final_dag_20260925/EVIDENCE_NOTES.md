# Evidence and residual latency

## WS evidence

Official page consulted 2026-09-25:
https://docs.polymarket.com/market-data/realtime-data
The former /developers/CLOB/websocket/market-channel redirects to this page.
The book and price_change schemas expose timestamps and hashes. No causal
sequence/inclusion guarantee for a later-received pre-snapshot delta was found
in the consulted documentation. This is absence of demonstrated proof, not a
claim that no such guarantee could ever exist.

Installed polymarket-client 0.11.0:
_internal/streams/clob/market_protocol.py: parse_events delegates to model parsing;
match_for filters token identity. It does not prove snapshot/delta supersession.
Two actual wire diagnostics establish same-token offsets -16 and -15 ms and no
accepted delta since snapshot, but do not establish causal inclusion. Retain
PRE_SNAPSHOT_DELTA_SUPERSESSION_UNPROVEN / BOOK_REGRESSION. No numeric tolerance,
no ignored delta, no last_valid_book_ms refresh, no WS semantic commit.

Tests: both observed offsets; later delta; older full-book; wrong market/token;
connection generation reset; equal timestamp; ambiguous timestamp; multi-token
preflight; empty and crossed books. The 'ignore if proven' branch is deliberately
NOT implemented because proof is unavailable.

## HTTP and concurrency inspection

Both network_readonly.GetOnlyTransport and collateral_onchain.PublicRPC use a
new urllib opener per request. Installed Python 3.13 AbstractHTTPHandler.do_open
constructs a connection and sets Connection: close. Therefore no persistent
HTTP session/pool is used on these paths. DNS/TCP/TLS durations were NOT separately
measured and cannot be inferred from elapsed_ms. No proxy/environment/provider
configuration changed. Pooling is a candidate for a separately tested transport
change, not a gain claimed by this instrumentation-only commit.

Inventory independent calls already run with a bounded eight-thread executor;
account calls use asyncio.gather; B/C calls use asyncio.gather AFTER account.
There is no sleep between seal/account/rechecks/evaluation. WS warmup happens
before selection of C, not as a readiness retry. Final checkpoint is already
after evaluation; failure is reported, leaving the older durable cursor usable.

## Measured PREVIOUS and NEW status

Previous target run 162216:
Preparation from durable cursor 94431065 through B 94432121: outside final window.
Final fixed tail B+1..C=94432122..94432130: 570 ms from real scan start.
Seal C: 226 ms. Parallel account: 291 ms. Parallel post-account rechecks: 268 ms.
Reconcile/evaluate: 7 ms. Total: 1362 ms.
Book sample at evaluation: 0 ms at millisecond resolution, not proof of zero CPU.

NEW network latency: NOT_MEASURED. DAG and causal dependencies unchanged.
New fields separate response_received_ms (body completely read), parse_complete_ms,
finished_ms, thread_cpu_ms, reconciliation timing, evaluation start/end/CPU.
proof completion remains critical_path.boundary_evaluated_ms. No source timestamp
is assigned from any new instrumentation field. HTTP/session behavior unchanged.

No p50/p95/p99 from a single run. Current measured network waits dominate the
7ms local finalization. This does not prove all future reads intrinsically need
>500ms, nor that moving to a VPS would solve the contract. The sequential post-seal
291+268+7=566ms is a real miss on this sample; its replacement by max()+7 would
weaken fixed-C's post-account reorg witness. Old scan observations loaded from
checkpoints also remain subject to 500ms, even if final local evaluation is fast.

## Separate later benchmark plan (NOT executed)

Same commit/provider/region/allowlists on current machine and a proposed host;
no migration, credential creation or monetary method. First compare public RPC
only, cold vs reused-connection candidate, bounded rate and identical numeric
block targets. Then, only with separately available authorized stored L2 on that
host, compare existing authenticated GETs. Never transfer secrets in reports.
Capture request/body/parse/thread-CPU and phase times, error rate, stale rate,
canonicality failures, actual connection reuse and clock provenance. Do not pool
all methods into one latency distribution. Predefine a modest sample budget;
report raw samples and median, p95 only with sufficient samples, no p99 claim
from a small diagnostic batch. Reuse must preserve allowlists, no redirects,
no retries on ambiguity, size/time bounds and redacted exceptions.

No host is selected or deployed, and no benchmark is launched in this phase.
The next single manual qualification is diagnostic, not a promised <500ms PASS.
