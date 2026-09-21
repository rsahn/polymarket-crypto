# Process writer candidate — technical evidence and integration contract

Status: candidate only; backend unchanged. No live collection, D6 or PAPER started.

## Evidence

Identical public technical capture: 77,477 messages. Reference full_stage_profile_20260921_154248: 46.3429475 seconds. One-message process writer process_writer_profile_20260921_155019: 41.6890016 seconds. Batch writer batch_writer_profile_20260921_155208: 34.0129629 seconds including spawn/drain, 2,277.87 messages/second. About 26.6% less elapsed time than reference on this measurement; not a statistically established speed gain nor proof of live capacity. No BTC/live networking in these benchmarks.

Both variants enforce contiguous sequence numbers, count all messages, and wait for worker completion. Each has a new technical_only.db. Exact readonly persistence comparisons cover events, book_sides, anchors and markets; exclusions limited to session_id and technical close wall time. Never claim these fixtures are prospective data. Reports live beside each benchmark.

Queue capacity: eight queued batches of 32, plus up to one producer batch and one consumer batch (not a total bound of 256 resident snapshots). Payload size also needs a bound in live implementation. Technical producer blocks on backpressure; no record dropped. Producer Queue.put timing includes copying/IPC scheduling/backpressure and must not be described purely as disk wait.

## Required implementation before adoption

1. One worker owns Store, Observer and BTCFeatures. Parent owns network/discovery/ingress. No SQLite connection crosses processes. Preserve current schema and JSON/zlib codecs.
2. One total sequence for every command: activation, rotation, reconnect, BOOK, BTC, clock sample, expiry, stop. Parent cannot bypass the worker with direct writes. All commands receive acknowledgments/checkpoints; a lost worker or mismatched sequence is fatal, never an implicit restart or reconnect.
3. Raw receive timestamp is taken at actual ingress and never rewritten. Add separate enqueue/processing/ack monotonic timing. Available time is assigned when worker actually handles data, clamped by existing temporal rules, never retrospectively set to captured receive time. The technical benchmark intentionally reuses captured observation times for equivalence; DO NOT copy that behavior into live operation.
4. BTC features use only observations available by anchor processing time. Retain raw snapshots/depth/source metadata/rejects. Generation, expiry and post-stop controls remain effective across queued commands. Backlog across expiry must be retained as explicit rejection rather than silently accepted or discarded.
5. Batch at most 32 with a short monotonic flush deadline independent of new arrivals; control barriers flush immediately. Bound items and bytes. Queue pressure, high-water mark, oldest queued age, sent/processed/committed sequence, stage throughput and worker health are visible.
6. Stop network ingress once, enqueue stop fence after earlier commands, drain FIFO, close all anchors, commit, acknowledge, join normally. Do not terminate a live writer because a wait timed out. Process death, failed commit, undrained queue or missing ack cannot become PASS.
7. Tests: semantic equivalence versus sync implementation with frozen clocks, batches of 0/1/31/32/33 items, quiet-tail flush, generation changes with backlog, stale/post-expiry payloads, BTC causal features, mid-batch exception, worker failure/queue-full detection, ordered clean stop, exact once sequence and zero trading. Complete existing suites plus new failure tests, audit/integrity/FK/double replay on synthetic fixtures.
8. Only after adoption criteria pass: freeze code/protocol, new NTP gates and new >=20minute SHADOW NO_TRADE500 smoke. Never reinterpret historical FAIL or existing smoke results. No long run until measured live latency and capacity assessed honestly.
