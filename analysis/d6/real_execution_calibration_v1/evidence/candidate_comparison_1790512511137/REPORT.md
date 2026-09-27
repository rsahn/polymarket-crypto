# Two-candidate GET-only comparison — CALIBRATION_BLOCKED

User rule: choose from convergent fresh evidence, not by assumption or manual preference. This supersedes the earlier request to pick an address. No reconciliation account has been bound because the required evidence is insufficient.

## Identity and request construction

- Identified signer/EOA: 0x9348efd557a09e644795c8f114bcf0bef86f203a.
- D6 candidate: 0x871d37b430c42ddbd0bbd37c29c02a2974109de9.
- Exact IDs were confirmed against PHASE6_ASSESSMENT.json, validated read-only genesis, existing public signer binding and pure installed SDK derivation/classification BEFORE requests. This confirms candidate identity/relationship, not current funds.
- SDK 0.11.0 classifies EOA as signature type 0 and this deposit as type 3. The GET balance builder supports signature_type, but no explicit wallet/funder argument or account echo. Both contexts were supplied per diagnostic request only. No .env/global signature type or execution account was changed.
- Same EOA-bound existing protected L2 triplet authenticated seven GETs. No SecureClient/key creation/derivation/rotation, private-key object, order signature or allowance mutation. The inseparable /balance-allowance GET was used for its balance field ONLY; allowance fields were ignored and not reported.

## Actual observations

Main probe: 2026-09-27 12:35:04.870–12:35:11.135 UTC (14:35 Paris).
Supplemental public history: 12:39:37.824–12:39:38.591 UTC.
**18 actual collection GETs: 16 main + 2 history, of which 7 authenticated. Zero HTTP POST/RPC POST, zero retries, no 429.** Documentation fetches are separate from these audited collection counts.

| Observation | EOA …203a | D6 context …9de9 | Scope/qualification |
|---|---:|---:|---|
| CLOB collateral balance, first and repeat | 0 / 0 raw | 109160000 / 109160000 raw | Signature-type contexts, no account echo |
| Documented unit conversion | 0 pUSD | 109.16 pUSD | Six decimals documented; contract 0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB |
| Data current indexed positions | 0 | 0 | Address query, archived included; one terminal page each; not global completeness |
| CLOB open orders in available credential view | 0 | 0 | One shared signer-credential request, partitionable by returned maker; no wallet-global guarantee |
| CLOB selected-market trades | 0 | 0 | Same signer credential view, current selected 5-minute market/slot only; raw pre-SDK attribution remains enforced |
| Data address trades, last 30 days | 0 | 0 | All markets in bounded window, not selected market only |
| Data address trades, start epoch 1 | 0 | 0 | Bounded all-time-requested sample; one terminal page each, NOT proof of global historical completeness |
| Explorer indexed pUSD balance | UNKNOWN | UNKNOWN | Both token-balance GETs returned []; absence is NOT zero |

Data requests used <=2 pages of <=50 rows, stable filters and exact returned-wallet/market/token/time validation. No unnecessary raw history was persisted. Empty views do not prove global flatness or absence of all historical trades.

Data /v2/status reported computed_at 12:34:54Z, age_seconds 11, serving lag 4s, custody balances 0s/1 block behind, ingestion blocks 94538235–94538236. This is recent service-level telemetry, not a per-account snapshot/mutation boundary.

The Blockscout address-token-balance responses were empty (both response digests equal the SHA256 of []). They therefore do NOT corroborate either address's current pUSD balance or metadata. In the original comparison JSON, explorer symbol/decimals fields name the REQUESTED/DOCUMENTED target, not returned token metadata. The reader now labels these requested_symbol/documented_decimals/token_metadata_observed explicitly. Original evidence was not rewritten.

## Verdict and exact missing capabilities

**CALIBRATION_BLOCKED; account=null; signer remains EOA.** The strong positive observation is a stable 109.16-pUSD balance in the SDK deposit-type context, versus zero in the EOA-type context. It is NOT yet an independently address-bound fresh balance for the exact D6 candidate. A derived address, old genesis, type selector, or empty index page cannot replace this missing correlation.

Missing: (1) GET-only pUSD balance evidence explicitly tied to each candidate address with a recent state block/time, permitting corroboration of the CLOB type-context result; (2) demonstrated per-account index scope/freshness, not just global service health; (3) account-wide order scope or an explicit adequate scope contract rather than assuming one signer credential sees every wallet order. No contradictory zero was manufactured from the empty explorer result. No manual address choice is requested; no automatic binding or trading qualification was issued.

The original startup execution conflict guard remains intact. No config/flags/V1/caps changed. No funding, approval, order, cancel, transaction, order signature, worker, arm, installation, commit or push.

## Artifacts and verification

- comparison.json: full sanitized candidate matrix, scopes, query contexts, timestamps, response hashes and request audit.
- history_all_time_sample.json: public-only bounded broad-history follow-up; no credential access.
- Source: compare_accounts.py; tests: test_compare_accounts.py. Existing raw CLOB validator reused unchanged.
- Final full inspected bounded offline suite: **346 passed in 14.48s**.
- Focused comparison + round6 + trade suite: **92 passed in 2.73s**.
- Exact prior readers: **43 passed in 0.48s**. Suites overlap, not additive. Not a full-repository-green claim.
- git diff --check: no whitespace error; existing unrelated CRLF warning only. Pre-existing tracked modifications preserved.

Public documentation reviewed: Polymarket wallets-auth; Data API v2 overview/migration and machine-readable contract; current-position and user-trade route references; installed SDK account builders/classifier; Blockscout public account/read API documentation. No RPC POST fallback was used when explorer evidence was insufficient.
