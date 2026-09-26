# Prospective harness integration contract — 2026-09-26

Status: OFFLINE_SYNTHETIC_INTEGRATION_ONLY. Real collection and real economic loading
remain blocked. This document supplements, and does not replace, PROTOCOL.md or
the immutable baseline_20260926 evidence. criteria.json is unchanged.

## Proven incompatibilities with the unchanged V1 observation contract

The exact runner's execute_signal computes entry fills before its second sleep.
NO_EXIT_BOOK / NO_EXIT_DEPTH returns before record_fill. MARKET_ROTATION also
omits the computed entry from the fill callback. record_fill, when called,
contains a VWAP and aggregate quantity, not each price level, entry clocks or the
entry book. A passive consumer cannot reconstruct missing observations without
inventing them or recomputing decisions.

The unchanged fill function does not consume the input levels. Repeated calls
against the same snapshot can fill the same volume again. The protocol requires
persistent counterfactual consumption. A passive adapter must reject an observed
fill exceeding that budget; silently resizing it would change V1.

Executable tests use the unchanged AST on synthetic inputs to prove both facts.
No tracing, monkeypatch, wrapper or callback is installed in the real runner.
No new scheduler or signal implementation has been introduced.
The adapter therefore DOES NOT constitute the requested complete real V1 binding.

## Fee qualification

Official primary sources, read on 2026-09-26:
- https://docs.polymarket.com/trading/fees
- https://docs.polymarket.com/market-data/market-details
- Public Gamma market endpoint recorded in evidence/harness_20260926/PUBLIC_FEE_EVIDENCE.json.

The public BTC 5m market 4961058 returned feesEnabled=true, feeSchedule rate=0.07,
exponent=1, takerOnly=true and feeType=crypto_fees_v2. Token membership is captured.
This proves applicability to that sampled market, NOT to all future markets.
The fee schedule is versioned by endpoint response digest, retrieval time and
feeType, not by silently interpreting makerBaseFee/takerBaseFee as the rate.

The fee documentation defines share quantity times rate times p(1-p), USD stablecoin
fee units and five decimal places, with makers uncharged. It does not establish
an exact tie-breaking and match aggregation procedure for this harness.
Installed SDK order/math.py ROUND_HALF_EVEN is order amount rounding, not evidence
for exchange fee rounding. No rounding rule has been admitted to the reviewed
production registry. Supported-rounding fixtures are explicitly SYNTHETIC_ONLY.
Unknown market, token, enablement, rate, schedule or rounding fails closed;
there is no default-zero fee. Synthetic cash fee accounting is not an assertion
about exact production exchange settlement mechanics.

## Journal / accounting / adapter

DurableEventJournal is one OS-locked writer per file; sequence starts at zero.
Each record has all mandatory identity and economic fields (null for fields not
applicable to an observation), previous hash and SHA-256 of canonical JSON.
source <= recv <= decision <= event; event timestamps never regress. Supplied
book timestamps cannot be future to the decision. Source clocks are never retimed.
The object acknowledges only after full write, flush and fsync. On short write or
fsync failure it is poisoned. Torn journal recovery refuses rather than truncating.
A process-crash test exits immediately after fsync and reopens the same fixture.
These are OS-level tests, not a hardware power-loss certification.

ProspectiveEventAdapter validates a detached copy of ledger/depth state first,
appends durably, then publishes state. Recovery deterministically reapplies the
accepted journal. It never invokes V1, a feed, a scheduler or an SDK.
Its inputs must be complete observations, not inferred fills.
An invalid observation does not advance the ledger.
FEE annotations reference a fill and never debit twice.

Per-token, per-side, per-price visible and remaining depth persists across
observations and restart via journal replay. Identical snapshots do not replenish;
only positive observed displayed-size changes add budget, capped by current
displayed size. Removal leaves a zero tombstone. Reappearance is a newly observed
increase, not a forecast. The model is a conservative counterfactual convention,
not a proven venue queue-position model. Exact observed fills are validated at
their prices; an insufficient budget rejects the experiment, not the V1 decision.
Historical DBs are never opened for writing.

Cash fee accounting uses average cost; reservations are a subset of cash.
Equity = cash + net liquidation value
       = 500 + realized net PnL + (net liquidation value - open cost basis).
Unmarked positions have unknown equity, never zero equity. Outstanding positions
or reservations, or a missing SESSION_END, prevent an economic PASS.
An explicit valid mark is required at each economic event time to qualify
drawdown. Actual causal mark production remains part of the missing binding.

## Partition sealing and statistical evaluation

The loader is explicitly fenced to synthetic manifests. Real loading raises
REAL_V1_BINDING_NOT_QUALIFIED. It has no collection entry point.
Within fixtures, source seal and manifest hashes are checked, a closed partition's
hash is verified, upstream results must be PASS and bound to first-access markers,
and PRE_VALIDATION / PRE_OOS freezes bind all prior result hashes, source seal and
manifest. First access is exclusive-created and fsynced before data exposure.
Any parse/validation/crash failure after that point consumes access permanently.
These are application audit guards, not filesystem ACLs against the file owner.

evaluate_partition loads criteria from the dependency seal, derives interval
bounds from the sealed manifest, and accesses data only through this loader.
No true dataset was accessed. Every test input is synthetic.
The evaluator retains empty calendar hours and computes the fixed circular
moving-block bootstrap (6h and 12h, 10,000 replicates, seed 20260926).
The empirical lower quantile uses the inverse discrete CDF without interpolation.
Any zero-denominator replicate or inadequate duration is INCONCLUSIVE.
PASS / FAIL / INCONCLUSIVE branches are tested without changing criteria.
The fixed criteria remain the authority; synthetic PASS is NOT an edge claim.

Remaining real reporting limitations: complete causal marks, spread/slippage,
latency and liquidity attribution depend on entry observations V1 does not expose.
by_liquidity is explicitly UNQUALIFIED rather than fabricated.
The implementation retains full journal/state history in memory and copies state
for validation; weekly throughput and memory feasibility are NOT qualified.
It must not be deployed as a weekly collector on the strength of unit tests.

## Storage and T0

Evidence: smoke_20260922_194254/review/RUN_MANIFEST.json source bytes 4,800,663,552;
COLLECTION_RESULT.json useful duration 1320.0542836000677 seconds.
No historical economic result is used in this estimate.
Extrapolation to 168h is about 2.20 TB for that observed collector workload.
An engineering planning reserve is twice that observed throughput plus 20%;
this is NOT a measured peak bound nor a proven single-5m sizing.
Journal and checkpoint volumes remain unqualified; therefore the preflight reports
DISK_CAPACITY_UNPROVEN independently of DISK_SPACE_INSUFFICIENT.
No data was deleted or storage purchased.

T0 remains UNBOUND. The implemented planning function refuses false gates, and
only after all other gates pass would pick the UTC 5m boundary at least 10 minutes
ahead. Durations stay 72/48/48h, embargo 60s, whole-market feature/label purge.
No absolute prospective boundaries, access markers or real dataset were created.

## Readiness and safety

The preflight compares V1 / runner / criteria hashes and the tested source seal;
it binds full-suite status to its log hash. It explicitly fails real adapter,
fee, partition/freeze, fresh two-reference clock and capacity gates.
It cannot return READY merely because tests pass.
SYSTEM_READY and current_inventory_proven remain false; this harness does not
read or alter Genesis, post-C completeness, technical readiness or monetary state.
REAL_ORDERS_ENABLED=false, LIVE_EXECUTION_ARMED=false, submit_allowed=false.
No real order, cancel, allowance update, transaction or private-key use.
