# Offline timestamp repair, bounded reconciliation and fee-contract review

**CALIBRATION_BLOCKED. No account requests/RPC sampling, monetary client, order signature, order/cancel/transaction, approval, funding, arming or operator acceptance.** Four unique official public documentation pages and installed SDK source were inspected. Windows Time status was queried locally without reconfiguration/resynchronization. Existing V1, caps, flags and execution guards remain unchanged.

## 1. P2 timing defect repaired

The preceding bound_diagnostics.py stage completion timestamp could rejuvenate early pages. observation_timing.py now records each operation's start/end and each page's read start, receive time (or explicitly labelled return upper bound), end and producer timestamps. Producer observed/source timestamps are retained rather than overwritten.

The freshness anchor is the **oldest justified producer timestamp/read start**, not completion. It controls the five-second lifetime and AccountAdapter's cached-reader checks. Slow balance calls and old first pages are unavailable even when the last response is recent. Market expiry during collection invalidates the observation, prevents subsequent reads and blocks projection. Legacy completion-only timing lacks the required new schema and is not accepted by the new projection. Older artifacts remain unmodified historical evidence; they are not re-stamped or requalified.

Controlled-clock tests cover >5s balance latency, multi-page delay, old/new/future/invalid producer timestamps, expiry crossing, stopping reads after expiry and conservative projection. The fix was not followed by another account sample in this offline pass.

## 2. Executable bounded-experiment contract — separate, not weaker full-wallet qualification

bounded_reconciliation.py implements **BOUNDED_EXPERIMENT_RECONCILIATION/1**, scoped to explicit experiment assets/intents rather than a wallet-global atomic snapshot. It actually reads verified existing Journal/CalibrationLedger recovery data. It retains every durable intent, including unknown/unacknowledged outcomes, checks sealed identity, FAK/entry caps, reservations and existing FeeRisk limits; local stop reasons remain blockers.

Qualified source records are required for a pinned cash/asset baseline and closing state, token/contract/unit mapping, bounded event coverage, canonical/finality/hash-recheck policy, native execution effects, cumulative terminality, receipts and an actual named operator declaration. There is no default verifier and no generated authority assertion. Missing real records remain UNKNOWN.

Implemented checks include exact raw-unit conservation; cumulative partial BUY/SELL fills; native cash/share fees and original reservation limits; terminal timestamps after fills and before closing reads; finalized-height/canonical consistency and a post-snapshot recheck; foreign order/trade/asset/mutation detection; WS gaps and incomplete pagination; exact receipt links; and operator identity plus the explicit limitation that a declaration does not prove other keys absent. Existing cash receipt reconciliation is reused. ERC1155 TransferSingle/TransferBatch deltas for the declared asset set are decoded and cross-checked, not promoted to wallet completeness.

Even a successful fixture result is **BOUNDED_MATCH_UNDER_ASSUMPTIONS_NOT_FULL_WALLET**, with no entry/arming permission. It does not call Ledger.reconcile, change reconciled/ready flags or satisfy the old full-wallet scope gate. A test with an accepting fixture authority still gets PARTIAL_SCOPE from the existing AccountAdapter. Recovery/custody remains fail-closed.

### Remaining software integration (not hidden as an external requirement)

- A real qualified acquisition-to-record bridge is still absent. The validator is implemented, not an installed producer of actual complete coverage proofs.
- Production Exchange/native fee-event decoding and its provenance/ABI mapping are NOT implemented or qualified here. Tests use explicitly synthetic native-effect records/events. Linking a receipt or matching net deltas alone does not prove per-order fees; the executions record requires a separately verified decoder.
- Native notional/price mappings that do not exactly match the currently supported ledger representation are rejected, not rounded/guessed. A reviewed protocol-specific mapping is required for such cases.
- This bounded scope is intentionally not integrated as a replacement for the existing execution qualification. Any policy change would need separate explicit review, not automatic promotion.

Actual block-baseline assets, closing state, finalized canonical receipts, coverage and native effects were not acquired. All actual required records remain UNKNOWN. An independent new external backend is not asserted to be inherently necessary; a correctly qualified bridge can reuse existing readers where their contracts suffice.

## 3. Fee arithmetic and documented limitations

See SOURCES_AND_FEE_LIMITS.md and the stored source texts for the four official pages and SDK 0.11.0 findings.

fee_model.py provides exact rational calculations/validators for the SDK price-curve formula, explicit rate/exponent units, additive builder maker/taker fees, cash versus asset-specific outcome-share debits, BUY/SELL partial fills, supported rounding modes and conservative bounded two-leg aggregation. Builder wire bps and SDK-normalized fractions are distinguished. USDC is not silently relabelled pUSD. The raw fd.r/fd.e normalizer preserves decimal lexemes and rejects absent/duplicate/unsupported fields rather than inheriting a zero-fee default. Rebates are not used to reduce conservative reservations.

Every calculation profile/result is **FIXTURE_ONLY / NOT_APPLICABLE_LIVE**. Integer exponents 0..8, one explicit outcome asset and supported explicit rounding/component rules are an implementation subset. Unknown native debit modes, currency mapping, rounding stage/direction/scope, builder parameters, price range or finite partial count block. Mixed per-component production rounding or unsupported native price mapping needs additional reviewed software/contracts. No actual numeric fee ceiling, current market parameters or paid fee amounts were invented. CONFIRMED alone does not supply native fee effects.

## 4. Clock and operator action

1160 ms was measurement resolution/request uncertainty, not measured drift. clock_bounds.py implements explicit interval arithmetic; it emits no qualification. The existing 100 ms threshold is unchanged. Local Windows Time reported a root-distance term of 53.48915 ms, but source trust/metric semantics, drift/age/read error and exchange-relative generation/accuracy still need justified bounds. Nominal nanosecond precision and small phase offset are not UTC accuracy proofs.

NEXT_SAFE_PROCEDURES.md gives the precise next measurement procedure and a concrete no-money operator drill using existing watch/interactive-accept interfaces. The actual operator and a reviewed isolated DRILL host are required. No real challenge, human receipt, attendance or drill completion was fabricated.

## Tests and scope

Final inspected bounded suite: **506 passed in 16.70s**. Exact prior readers: **43 passed in 0.56s** (overlap/nonadditive). Includes adversarial journal/receipt/fee/currency/cumulative/foreign-activity/finality/timing tests, virtual round-trip accounting and unchanged full-wallet rejection/reservation policies. No full-repository or live-conformance claim.

Diff whitespace check: no error; pre-existing unrelated CRLF warning only. Earlier tracked modifications preserved. All original account/identity observations remain historical; current cash and actual qualification inputs were not re-sampled.

Files: observation_timing.py, bound_diagnostics.py, bounded_reconciliation.py, fee_model.py, clock_bounds.py; corresponding test modules. qualification_matrix.json separates implemented software, missing real source integration, unknown actual evidence and operator actions.
