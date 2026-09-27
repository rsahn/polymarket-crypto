# Validated D6 identity consumer and bounded observation adapter

**Identity binding consumed; CALIBRATION_READY=false, submit_allowed=false. No execution.**

## Binding consumer

binding_consumer.py explicitly imports the known historical unversioned ACCOUNT_IDENTITY_20260927_V0 profile into **D6_RECONCILIATION_IDENTITY/1**, preserving the original artifacts. It verifies source_digest, source semantics, exact D6 account/EOA signer, integer type 3, chain 137, collateral contract, scope, SDK 0.11.0, strategy hashes, timestamps/block consistency and all non-execution/no-override flags. Unknown versions, role changes, source paths, digest mismatches and future/invalid source times fail closed. The v1 runtime consumer revalidates the source and envelope, not just the new wrapper's labels.

The consumed binding has **current_cash=null** and **cash_reacquisition_required=true**. Its historical identity timestamp remains unchanged. Expired historical cash is never imported into the current observation. This is locally validated acquisition provenance, not a fabricated external signature and not protection against a malicious process with the same filesystem identity rewriting all sources.

Roles remain D6 **0x871d37b430c42ddbd0bbd37c29c02a2974109de9**, signer EOA **0x9348efd557a09e644795c8f114bcf0bef86f203a**, explicit diagnostic type **3**. No explicit READONLY_SIGNATURE_TYPE selector was observed in .env/process, so actual_signature_selector_conflict=false. The legacy EOA reader's generated type-0 context is separately marked incompatible; it is NOT misrepresented as an observed configured selector. .env, flags and startup guards remain unchanged.

## One real acquisition, no repeated sampling

**2026-09-27 13:42:41.792–13:42:44.123 UTC (15:42 Paris).**

Exactly **7 GETs, 3 authenticated**, all HTTP 200. **0 RPC / HTTP POST, 0 retries, no rate limit encountered.** Shared request budget 10, >=350ms serial pacing, <=2 pages/view; orders/trades <=200 returned rows, Data positions <=100. 429 stops further requests. The adapter is one-shot; reuse is rejected. No automatic refresh loop.

- Fresh balance GET at 13:42:42.697 UTC: **109160000 raw / 109.16 pUSD** in the validated D6/type3 context. No fresh chain read is claimed. The inseparable allowance fields were ignored.
- Open orders: **0 returned**, one terminal page, **available signer-credential view** only; every nonempty raw row must attribute to D6 before SDK normalization.
- Trades: **0 returned**, one terminal page, **credential view for btc-updown-5m-1790516400 / current slot only**. Raw market/time/role/account/order attribution remains enforced before SDK parsing. Validated reported price/share quantities are now retained; cash_fee/share_fee remain null, never invented as zero.
- Data positions: **0 returned**, one terminal page, explicit **user=D6**, current indexed positions across markets, archived included. Every row's wallet, token, condition, status and numeric size is checked before projection. Foreign, ambiguous or malformed later pages invalidate the operation rather than yielding misleading empty totals.
- Data service telemetry: age 10s, custody-serving lag 1s/1 block; some resolution cursors reported 623 blocks behind the maximum. Those global metrics do not establish a per-account frontier, and sparse-event cursor lag is not automatically interpreted as proof that this wallet's positions are stale or absent.
- Coarse clock: offset 48ms, uncertainty **1160ms**. This does not meet the fine-clock requirement.

These observations were within their local five-second age bound at collection end. **They are now historical and must not be reused as current cash/state.** A subsequent offline check consumed the identity successfully but rejected the persisted cash snapshot as expired. Empty pages/drained pagination were never promoted to wallet completeness, flatness or permission to execute.

## Concrete adapter wiring

bound_diagnostics.py constructs the existing actual **ReadOnlyClient** in explicit D6/type3 context, applies strict raw response validation, stages bounded views transactionally, and wires immutable copies into timestamp-preserving CachedReaders used by the existing **AccountAdapter.snapshot()**.

The real projection succeeded: account D6, observed cash 109.16, scoped empty position/order/trade sets. It explicitly retains inventory_proven=false, cash_proven=false, orders/trades/positions_complete=false and unqualified scope/frontier/baseline/fee blockers. The legacy combined collateral/fee blocker concerns full execution-state qualification; it does not revoke the verified historical collateral identity. No authority, signed proof or monetary SDK runtime was fabricated. Cached readers perform no network calls and reject stale observations.

## Capabilities and minimal next safe work

Existing queried APIs support: authenticated scoped balance; attributed credential order data; market/time-scoped trade data; address-indexed positions; market identity; coarse clock and service telemetry. This software now actually consumes and projects those facts.

The queried contracts do NOT supply a shared wallet snapshot/mutation watermark or verifiable common lineage. They do NOT establish that a credential view/index covers every relevant wallet mutation/asset/order. Draining cursors cannot add those guarantees. No independently final per-order native cash/share fee effects or qualified round-trip fee ceiling were established by this batch; a fee rate or CONFIRMED status is insufficient. Other potentially documented API surfaces must be evaluated on their actual contract, not declared universally incapable.

Minimal next safe work: **offline producer-contract/SDK audit and executable reconciliation tests** mapping the required baseline, coverage/lineage and native fee-unit/bound claims to available data. Establish a supportable reconciliation contract before asking more of the network. If a necessary guarantee cannot be supplied, retain its blocker; do not sample repeatedly or introduce a pretend proof service. No intrinsic new external backend is assumed. Execution-runtime qualification and actual operator drill/attendance/specific-exposure acceptance remain separate, unperformed requirements.

## Verification and files

Full inspected bounded suite **423 passed in 14.44s before the real GET collection**. Exact prior reader command **43 passed in 0.58s** (overlapping, not additive). IDENTITY_ONLY_CONSUMER_PASS and PERSISTED_OBSERVATIONS_EXPIRED_AS_EXPECTED verified with the actual persisted artifacts. git diff --check: no whitespace error; known unrelated CRLF warning only. Not a full-repository-green claim.

Source: binding_consumer.py, bound_diagnostics.py, observed_trades.py quantity projection; tests: test_bound_diagnostics.py. Artifacts: binding_v1.json, qualification_matrix.json, capability_assessment.json, this report. Earlier identity/cash evidence remains unmodified.

No credentials disclosed/created/rotated; no SDK monetary constructor, order signature, order/cancel/transaction, allowance operation, funding, arming, live worker, config/flags/V1/cap change, install or push. Pre-existing changes preserved.
