# Expected signer: identity unresolved, recovery blocked

The preview requires the explicit process variable `L2_RECOVERY_EXPECTED_SIGNER`, containing the historical D6 signing EOA public address (0x plus exactly 40 hexadecimal characters). It never reads .env, derives an address from a private key, or falls back to another wallet field.

Local inspection on 2026-09-25:
- L2_RECOVERY_EXPECTED_SIGNER: absent from process and project .env.
- READONLY_SIGNER_ADDRESS: absent from process and project .env.
- POLYMARKET_WALLET_ADDRESS: present in project .env, syntactically valid, masked 0x9348...203a. This alone is not evidence of historical signer identity.
- pre_live_check_d6.py historical versions d1f7cb5, 978d462 and e3f05d8 contain no literal public signer address. The current factory uses the SDK's private-key bootstrap with wallet omitted; it was NOT imported or executed. Its comment distinguishes the signer from the resolved deposit wallet.

READONLY_SIGNER_ADDRESS supplies the POLY_ADDRESS authentication header in qualify_local_readonly.py. POLYMARKET_WALLET_ADDRESS identifies the expected account/inventory wallet. The probe classifies their relationship via SDK classify_account and signature_type_for. Their equality is neither required universally nor established here. L2_RECOVERY_EXPECTED_SIGNER must identify the historical signing EOA independently; no automatic copy from the account wallet is allowed.

A valid syntax is not proof of historical ownership. Historical public signer identity remains unproven by the inspected local sources. Configuration was not changed. A public historical signer address with provenance/user confirmation is required before setting the dedicated process variable. No private key is needed for this configuration.

The existing Plan/RecoveryPolicy rejects an absent or malformed signer before any transition. The preview exits 2 and marks NOT_CONFIGURED. Five additional malformed-address tests pass, including a 64-hex-character value; 41 targeted tests pass overall. No production code change was needed. No new real preview was run because configuration is unresolved; existing reports were preserved. No network, signature, credential derivation or monetary call was made; both live flags remain false, BTC V1 and transport unchanged.
