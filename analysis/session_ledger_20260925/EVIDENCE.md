# Genesis-bound execution journal, offline validated

A new BoundExecutionStore implements the ExecutionStore contract in a separate database. It binds to the explicitly expected Genesis hash and journal head. Genesis is read-only. Publication uses fsync plus an exclusive hard link; no existing session can be replaced. Existing unbound execution databases are rejected, not migrated implicitly.

Every controller state and event now commits with its hash-chain entry in one SQLite transaction. Two connections cannot reserve an open session twice. Reopening checks the binding, event IDs, hash chain and snapshot equality. This detects inconsistent local edits, not malicious replacement of all data and hashes. A changed Genesis journal blocks further activity.

Tests exercise a complete fake controller cycle and reopen, event/state/chain tampering, deleted event, interrupted publication, mid-transaction failure, duplicate reservation, overwrite refusal, wrong Genesis and accidental Genesis-path reuse. All use temporary fixture databases, not runtime/d6_genesis.db.

RED: new module absent. GREEN: 43 controller/journal tests. Full suite: 697 passed, 8 subtests passed, 3 deprecation warnings. Boundary audit PASS. SDK monetary calls: zero. Scoped pattern leak scan: no hits. No credentials loaded and no production session file created.

Projection deliberately reports only last reported cumulative fills. It does not claim current remote inventory, reconciled cash, fees or PnL. A ledger alone cannot supply missing settlement evidence or the post-C common completeness boundary. Production account binding, settlement/cash projection and real target-network validation remain incomplete. Transport remains hard-locked; this is not a live-launch delivery.

The existing execution controller can receive BoundExecutionStore as its store (demonstrated in tests); no production runner is armed or constructed automatically.
