# D5.1 storage preparation — no collection decision yet

The active 22-minute smoke is unchanged. No source DB read for this preparation. No D6/OOS computation or performance selection.

Static inspection of analysis/d6/pipeline/convert.py finds an explicit omission: events.BOOK.payload_json is replaced by NULL. That export was designed as a derived view with raw SQLite retained. It cannot be promoted to the sole D5.1 evidence archive: it omits wire_event_ts_ms, source_metadata and additional snapshot metadata needed to reproduce the new timestamp contract. Existing tests verify selected rows/features, not byte-for-byte reconstruction of all source columns.

Requirements before adopting a smaller primary dataset:

1. Preserve every table/column, null/type, identity, event order, depth level, BTC tick, anchor lifecycle, rejection and wire metadata. No downsampling or dropped BOOK payload.
2. Lossless compression may deduplicate repeated values only with an explicit decoder and exact canonical row-stream equivalence including payload metadata, not merely similar feature rows.
3. Partition at sealed boundaries, retain checksums/manifests and crash-safe commit markers. Replay across every boundary must equal the monolithic reference. Do not splice generation or market identities.
4. Compare independent NoTrade decisions/full-state/result hashes on the complete export, and retain the raw source. Existing SQLite sources are never deleted to recover disk space.
5. Benchmark on a CLOSED admissible new smoke after audit. No conversion, scan or second auditor while the current smoke runs.
6. Forecast long-collection raw+WAL+derived+temporary peak storage from measured growth, conservative burst allowance and at least 5 GiB reserve. Do not assume Parquet savings without preserving all necessary data and measuring them.
7. Decide prospective duration/independent market targets before looking at D6 outcomes. A 20-minute instrumentation PASS alone is not a TRAIN/VALIDATION/OOS sufficiency finding.

Current evidence: light_monitoring.jsonl in smoke_20260921_092802 contains file logical/physical sizes, free disk and actual recorded counters. The first ~2-minute sample is too short to select a long-collection capacity. No duration or statistical sufficiency has been asserted.
