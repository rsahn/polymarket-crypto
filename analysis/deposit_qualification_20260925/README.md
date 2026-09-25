# Deposit wallet read-only qualification

Execution only by the user in the normal target-machine PowerShell:

    python -B .\analysis\qualify_deposit_wallet.py --target-machine

Output: new DEPOSIT_WALLET_READ_ONLY_<UTC timestamp>.json, exclusive creation (never overwrites).
No network execution was performed during development. Tests use fixtures and the offline socket guard.

Sequence: public CLOB /time (freshness <=5s), two public GETs to relayer-v2.polymarket.com/deployed with address=<SDK candidate>&type=WALLET. These are the same public reads used by SDK 0.11.0 _resolve_requested_wallet, with no secure client construction. Both candidates are computed from the confirmed PUBLIC signer through SDK CREATE2 functions; this is not credential derivation. Strict boolean deployment responses required; exactly one deployed candidate required. None, both, errors or malformed responses => no credential loaded and no authenticated request.

Proof scope: deterministic signer/factory association plus official relayer deployment observation. deposit_wallet_proven is scoped to that evidence, NOT an independent eth_getCode/owner reading, NOT proof of the exact historical snapshot. onchain_verified=false and historical_instance_proven=false remain explicit. If the relayer is inaccessible or contradictory, keep false and stop. No speculative GET RPC or JSON-RPC POST is attempted; an independently documented public on-chain GET source would need a separate probe if required.

After proof: existing DPAPI L2 validation/read only, one GET /balance-allowance with asset_type=COLLATERAL and signature_type=3. No wallet/token/spender query and no fallback. Compare integer raw with historical 109160000 without denomination conversion. Allowance selection is informational only; no update endpoint. Contract/decimals/account binding flags stay false.

Positions: corrected SDK /v2/positions request, lower-case include_archived=true, selected wallet as user, bounded pagination. HTTP 400 reports only allowlisted structured validation codes/parameter names and a body fingerprint; no arbitrary server message, input, address, credential or order ID is written. A recognized query validation issue is server-declared evidence, not a claim about deeper server behavior. If the body is unstructured, exact_cause_proven remains false. No endpoint fallback or speculative retry. Positions remain an index view, complete=false.

No dotenv, private key, L1 signature, credential recovery, secure client, deployment, monetary transport or live flag change. Flags are checked before any network; monetary transport remains locked. Existing comparative report was not regenerated or modified.

Sources inspected:
- Installed polymarket-client 0.11.0 clients/async_secure.py:_resolve_requested_wallet.
- Installed _internal/actions/relayer/deployed.py:fetch_deployed (GET /deployed, address/type).
- Installed _internal/wallet.py: public CREATE2 candidate computations.
- https://github.com/Polymarket/builder-relayer-client (getDeployed(walletAddress, "WALLET")).
- https://docs.polymarket.com/trading/wallets-auth.

Validation offline: 13 new tests; full suite 459 passed, 25 subtests passed, 0 failed/errors, 3 warnings. Static audit AUDIT_OK; 16 SDK monetary methods guarded, sdk_monetary_attempts=0. Both flags false. BTC V1 and the previous comparative report have no diff. RED.log records the initial missing-module test-first state, not a reproduced pre-existing bug. No real network observations produced in this phase.
