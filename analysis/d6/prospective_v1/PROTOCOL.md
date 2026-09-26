# BTC V1 prospective validation â€” phase 1

Status: BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED. No collection, no economic evaluation,
no OOS access. This directory is separate from the immutable V1 and D6 technical code.

## Identity
The two user-provided SHA256 values are mandatory. prepare.py stops with
STRATEGY_IDENTITY_CHANGED before writing if either differs. STRATEGY_MANIFEST.json
captures both, their configuration, the collector/backend source closure (a
conservative superset), dependencies installed in this interpreter and Python.
This captures current bytes, not a claim that historical results used these bytes.
No credential/config environment dump is performed.

## Accounting
core.Ledger is a tested OFFLINE kernel, not a collector-ready runner.
FIFO order of timestamped events; equal timestamps use call order/event IDs.
Gross purchase cost is basis. All paid fees immediately reduce realized net PnL.
Sales realize proceeds minus proportional basis minus fees.
Cash contains reserved cash; available=cash-reserved.
Equity=cash+net liquidation value=initial+realized_net+unrealized_net.
The phrase MARKED_OPEN_POSITIONS in the user invariant means unrealized PnL,
not total market value (otherwise invested principal would be counted twice).
Unknown mark => UNRESOLVED_POSITION and equity unknown, never position deletion.
No-exit-book, rotation or no depth must retain acquired positions through resolution.
A resolution must have public evidence available before settlement; expiry alone
is not resolution. The kernel caller must verify that evidence and token identity.

Fixed25 means purchase principal up to 25, fees in addition; reserve principal plus
a conservative fee envelope before attempting a fill. Insufficient cash is an
explicit rejected/reduced entry, not borrowed cash. No parallel sizing affects it.
The historical signal's first BTC tick within the last 250 ms, >=5bps, 1000ms global
cooldown, direction and nominal 250ms+500ms delays remain unchanged.
No current V1 source was edited. A future adapter must prove identical opportunity
and scheduling decisions on synthetic traces before it can activate this ledger.

## Fees
Sources inspected 2026-09-26:
https://docs.polymarket.com/trading/fees
https://help.polymarket.com/en/articles/13364478-trading-fees
https://docs.polymarket.com/market-data/market-details
Official formula: shares * rate * price * (1-price); published crypto rate 0.07.
Public documentation describes five-decimal precision; the Help article is dated
2026-07-10. Exact tie-breaking, aggregation granularity and applicable per-market
configuration must be bound to retained evidence before net qualification.
FeePolicy currently uses ROUND_CEILING at 0.00001 as a conservative simulation
upper bound, NOT as a claim about the exchange's exact rounding.
No zero-fee fallback. No rebates assumed. The verified flag in synthetic fixtures
is not a production attestation. NET_EDGE_UNQUALIFIABLE remains a launch blocker.
No private keys, accounts, signing, SDK execution or monetary endpoints needed.

## Causality / schema
schema.json defines required persisted fields. BookTape rejects future timestamps,
duplicate identities and availability regressions. It selects only observed books.
Depth consumption persists across identical snapshots; increases in visible size
alone credit renewal. This is a conservative counterfactual model, not proof of
the true queue. Token/generation/expiry/cross-market and source clock uncertainty
must also be checked by the prospective adapter, not inferred by this kernel.
A signal at a rotation follows frozen V1 semantics; never silently bind it to a
different rule to improve results. Every decision and rejection must be retained.
Settlement and marks cannot alter prior decisions.

## Boundaries / criteria
criteria.json freezes a seven-day pilot: 72h TRAIN / 48h VALIDATION / 48h OOS.
Rationale: several daily cycles plus weekday/weekend; no claimed power calculation.
Minimal samples and uncertainty criteria were chosen BEFORE new data, not from
the old performance figures. No V1 optimization. No extension if inconclusive.
An actual start is deliberately UNBOUND while launch blockers remain.
DATASET_MANIFEST.json is explicitly a PREPARATION manifest, not a launched dataset.
The future freeze must select the next UTC five-minute boundary at least 10 minutes
after all launch gates PASS, record that absolute start and planned end before any
capture, and exclusively create the launch manifest. A missed start invalidates
that launch; it cannot be shifted silently.
Only full markets whose feature-to-label interval lies in one split are eligible.
60-second embargo at internal split starts. Unresolved settlement crossing a split
cannot be filtered by winner/outcome: retain the position and block qualification.
Future market registry must bind condition/tokens/expiry to the prespecified universe.
Old DBs and results are excluded, including the non-admissible Sept22 exploration.

## Freeze and first access
Seal checks byte hashes; write_once uses exclusive create plus fsync.
AccessGate requires upstream PASS, matching code/dataset seal, and consumes access
before evaluation. A crash leaves the marker consumed, hence INCONCLUSIVE rather
than an automatic rerun. Results are write-once. This is an audit guard, not an ACL:
a production loader/evaluator MUST exclusively route partition access through it.
No such loader is claimed delivered in this first iteration. prepare.py cannot
collect or evaluate. A PRE_OOS_FREEZE must bind results, all hashes, criteria,
actual OOS boundary and first-access marker before any OOS reading.
The first-access marker stores a canonical copy of the caller-supplied freeze.
Production must verify its full required schema before this low-level gate is used.

## Blocking evidence and implementation boundaries
1. Exact market-bound fee/rounding evidence is not yet established.
2. A parity-tested adapter for frozen V1 callbacks and a durable causal event/ledger
   journal are not integrated. core.py alone is not a production execution model.
3. The metric evaluator and hidden-partition loader must enforce the access gate,
   block-bootstrap definitions and terminal reconciliation end to end.
4. A bounded lossless prospective storage plan must fit free space; only ~48 GB
   was available at preparation. The seven-day lossless volume is unqualified.
5. Absolute launch boundaries, prospective dataset hashes and admissibility gates
   cannot be attested before the above pass. They are not fabricated.
These are explicit readiness failures, not user authorization requests. No launch
command is supplied while BLOCKED. No claim of net edge or SYSTEM_READY=true.

## Tests / execution
python -B -m unittest analysis.d6.prospective_v1.test_protocol -v
Only synthetic temporary data. RED was ModuleNotFoundError before core.py existed.
Full project suite uses the existing offline validate_execution.py harness, which
blocks external sockets and monetary SDK calls and fixes live flags false.
Existing V1, Genesis, inventory, worker, CLOB, WS, risk/readiness are protected.
