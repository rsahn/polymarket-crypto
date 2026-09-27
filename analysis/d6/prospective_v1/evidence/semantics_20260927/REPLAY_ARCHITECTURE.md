# Replay state and limits

The new candidate streams one journal line at a time, verifies the original schema, identity, sequence, timestamp order and hash-chain, and indexes all event IDs in a new SQLite scratch file (2 MiB configured page cache). It then calls the unchanged adapter recovery transition. Source journals are read-only; no strategy/collector/partition entry point is called.

This is **STREAMING_INPUT**, not **BOUNDED_STATE**. A line has no schema size cap, so even input RAM has no finite protocol-wide bound. SQLite cache configuration is not a proof of maximum process RSS. The economic adapter still retains history; candidate is not adopted.

| Necessary state | Why it must survive / storage option |
|---|---|
| cash, reservations, positions, cost basis, realized PnL, fees, turnover, last ledger timestamp | Exact economic transition; working ledger |
| market/token/trade stage and per-trade quantity | Callback-order checks and oversell prevention; disk map possible |
| displayed and remaining depth by token/side/price, tombstones | Existing persistent model; cannot reset by time |
| causal book history or an indexed as-of lookup | `BookTape.at(token,decision_ts)` can query an earlier decision timestamp; only keeping latest is not generally equivalent |
| fill ID to fee lookup, annotated IDs | FEE can reference an arbitrarily old fill; no finalization bound exists |
| all seen event/trade/ledger/book IDs | Reject later duplicate; discard requires exact external index, not a bounded recent cache |
| partition identity, sequence, previous hash, last event time, ended | Identity, ordering, end fences; partition transition must remain explicit and closed |
| accounting output | Can stream to an immutable output sink in a future separate implementation; current downstream contract still expects a list |

A finite protocol-sized state bound is not established: accepted keys, book levels, event text, annotation lag and number of historical trade identities have no frozen caps. Disk-backed indexes can externalize growing history without changing economics, but that adds unbounded disk demand and requires its own equivalent adapter/storage contract. No unsafe truncation, eviction or silent dictionary pruning is implemented.

Recovery equivalence is tested at three prefixes of the complete 20-event journal (including open position, partial exit/residual and settlement/session end). Corruption, duplicate, torn and cross-partition records reject. Performance of a new candidate on the existing MARK journal is a technical comparison only; never a week extrapolation.

The former ~59.67 ms state-copy @5000 result remains evidence for live `observe`; this candidate uses the existing replay `_apply` path and does not repair live transactional copying. **REPLAY_CAPACITY_UNQUALIFIED**.
