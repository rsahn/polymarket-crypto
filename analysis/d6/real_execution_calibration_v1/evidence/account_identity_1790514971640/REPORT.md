# ACCOUNT_IDENTIFIED — D6 reconciliation account, EOA signer

Explicit narrow authorization covered only Polygon read RPC chain identity/block headers and eth_call for the confirmed pUSD contract's metadata and the two candidate balanceOf calls. Existing GET authorization covered necessary contemporaneous CLOB balance corroboration. It did not authorize any monetary action or broader RPC.

## Fresh evidence

Observed **2026-09-27 13:16:07.013–13:16:11.638 UTC (15:16 Paris)**.

- Signer/EOA: **0x9348efd557a09e644795c8f114bcf0bef86f203a**.
- Selected reconciliation account: **0x871d37b430c42ddbd0bbd37c29c02a2974109de9**.
- Both addresses and exact collateral contract were checked against existing artifacts, the validated local genesis/public signer binding, and SDK classification BEFORE requests. These checks supplied identity context; they were not used as a substitute for the on-chain balances.
- Existing public RPC returned chain ID **137**.
- Contract **0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB** returned **Polymarket USD**, symbol **pUSD**, decimals **6** via independently acquired eth_call results.
- All metadata and balance reads used the identical numeric block **94539886 / 0x5a2906e**.
- Block time **13:16:09 UTC**; hash **0x89a0679e2afc2a92689c895c1b78f3d2e2c0379fe5c3acabe2e1f1b0db1f69f1**.
- Header number/hash/timestamp matched the final recheck exactly. This is a pinned latest-block observation through the existing HTTPS provider, NOT a claim of final settlement or independent consensus verification.

| Candidate | CLOB GET before | On-chain balanceOf at pinned block | CLOB GET after |
|---|---:|---:|---:|
| EOA / type 0 | 0 | 0 | 0 |
| D6 deposit / type 3 | 109160000 | 109160000 | 109160000 |

Values are exact raw units. With observed six decimals: EOA **0 pUSD**, D6 **109.16 pUSD**. The authenticated GETs were made with the existing EOA-bound L2 credentials and explicit SDK-supported per-request wallet contexts. No absolute address echo from CLOB was required: matching direct address-scoped chain balances, authenticated before/after balances and verified derivation provide the missing corroboration.

## Decision and explicit binding

The user decision rule identifies **D6 as the economic collateral/reconciliation account and EOA as signer**. No ambiguous dual-funded/unknown case was forced into a choice.

Project-local **reconciliation_binding.json** records those distinct roles, explicit signature context **3**, chain/contract/block/provenance and the evidence digest. Digest and role integrity were checked after persistence. It is not a global config patch or automatic startup override. The cash sample has a short freshness lifetime; future live use must reacquire cash and the other required evidence. The historical account-identity evidence is not an evergreen portfolio snapshot.

Configured explicit READONLY_SIGNATURE_TYPE selectors were absent in the inspected .env/process whitelist. The legacy stored-L2 EOA qualification path builds type **0**; that legacy context remains incompatible with D6/type **3** and is explicitly recorded as legacy_eoa_context_conflict=true. No setting was silently overwritten or claimed to exist when absent. .env still names the EOA, and the original startup account-conflict guard still reports BLOCKED. Any later consumer must use an explicit validated D6/type3 context, not silently fall back to the old EOA/type0 reader.

## ACCOUNT_IDENTIFIED is NOT CALIBRATION_READY

calibration_ready=false; submit_allowed=false; automatic_startup_override=false.

This cash evidence does NOT prove positions absent, wallet-global open-order completeness, trade/settlement finality, mutation closure or a common inventory frontier. Those need fresh reconciliation evidence. Native cash/share fee attribution and round-trip fee ceiling, actual execution-SDK runtime qualification, fine clock qualification, operator recovery drill/attendance and specific-exposure custody acceptance also remain unqualified. No live strategy/worker/arming was started.

## Exact requests and safety

**8 RPC HTTP POST reads:** eth_chainId x1, eth_getBlockByNumber x2, eth_call x5 (symbol, decimals, name, two balances). Same existing repository public provider; no key in report. No eth_getCode/logs/receipt/sign/send/approval or arbitrary eth_call accepted by this reader.

**5 HTTP GETs:** /time x1 and /balance-allowance x4 for balance only. Four authenticated HMAC GETs. Allowance fields were ignored. No retry; serial pacing >=300ms RPC and >=350ms GET. All returned HTTP 200. Hard budgets: <=10 RPC, <=5 GET; stop on failure/rate limit. No new credentials, SDK monetary constructors, order signatures, orders, cancels, approvals, funding, transactions, global config/flags/V1/cap changes, install or push.

## Verification and source

- Source: identify_account.py; offline tests: test_identify_account.py.
- Method/target/selector/block constraints tested before real reads, including rejection of signing/sending, approval selector, foreign account, changed block, malformed ABI, wrong chain/metadata and stale/reorg headers. Read failure halts without retry. Both-funded/contradictory and inverse-account decisions tested.
- Focused RPC + candidate tests: **45 passed in 2.39s**.
- Full inspected bounded suite: **372 passed in 13.96s**.
- Prior reader command: **43 passed in 0.70s**. Suites overlap/nonadditive; not a whole-repository-green claim.
- BINDING_INTEGRITY_PASS. git diff --check: no error, only existing unrelated CRLF warning. Pre-existing tracked modifications preserved.

Artifacts: evidence.json (sanitized full acquisition matrix/audit), reconciliation_binding.json (explicit non-arming account binding), this report. Earlier GET-only insufficient-evidence reports remain unchanged as history; their economic-identity blocker is superseded by this new authorized on-chain corroboration, not their residual execution blockers.
