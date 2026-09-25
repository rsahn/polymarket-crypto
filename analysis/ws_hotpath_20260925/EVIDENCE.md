# Demonstrated WS hot-path CPU defect

The last target run showed long pauses after completed I/O. Profiling the actual ingest implementation offline identified a concrete contributor: every event called BookStateSource.read solely to obtain synchronized. That method deep-copied both complete books. The synchronization predicate is exactly connected and len(books)==2 and does not require materialization or freshness evaluation. StreamBook.read also called the base read twice; the second copied result was used only for reason.

Minimal fix: inline that same synchronization predicate in ingest; reuse the first base snapshot's reason in read. No parser, timestamp, regression, resync, freshness, liquidity, sizing, risk or decision rule changed. Final decision snapshots remain deep-copied and detached from subsequent events. No numeric tolerance or pre-snapshot delta exception added.

RED: failing test forbids full decision-snapshot materialization inside ingest. GREEN: test passes; snapshot independence is verified. Complete suite: 630 passed, 8 subtests passed, 3 warnings. Audit passed, zero SDK monetary attempts and no external socket attempts under guarded tests.

Reproducible synthetic profile: python -B analysis/ws_hotpath_20260925/benchmark.py. Fixed clock, two 198-level books, 2000 same-token deltas; cProfile enabled both times. BEFORE12.8404s; AFTER3.3319s (~74% lower profiled wall time). This is not a network latency benchmark or p95 claim. Baseline read/deepcopy cost9.596s cumulative disappears from ingest profile. Remaining update validation still runs for every touched book. No claim that all observed target delays are explained or fixed.

Equivalence against commit1392c9e: all fields of102 decision snapshots match for a deterministic sequence (see EQUIVALENCE.json). Existing tests cover stale500/501, malformed depth, identity, resync and pre-snapshot regressions. Genesis, BTC V1, fixed-C evaluator, production risk logic, monetary lock and500ms unchanged.

Remaining blockers cannot be waved away: target run must measure actual latency under wire load; the fixed-C proof still does not establish common post-C completeness, so current_inventory_proven remains fail-closed. No real order, signature, credential operation or target qualification performed here.
