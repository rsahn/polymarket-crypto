# Explicit archive RPC configuration

POLYGON_ARCHIVE_RPC_URL is optional process-environment configuration for the isolated analysis/diagnose_ctf_rpc.py diagnostic. No provider is assumed, no key is created, no URL with a secret is committed. config/polygon_archive_rpc.env.example documents the name with an empty value; neither it nor .env is automatically loaded.

Absent/empty => BLOCKED / POLYGON_ARCHIVE_RPC_URL_NOT_CONFIGURED before wallet calculation or any network call. Invalid URL => BLOCKED / POLYGON_ARCHIVE_RPC_URL_INVALID. HTTPS required; userinfo, fragments and whitespace/control characters rejected. URL path/query may contain an existing provider credential, held only in process memory and never included in reports, logs or exceptions. Redirects remain rejected. Report provenance is the environment-variable name only.

When explicitly configured by the user, the separate diagnostic verifies chain 137 then performs exactly one allowlisted historical CTF eth_getLogs request. There is no dRPC fallback. No dotenv/private key/L2 load. No production network was executed during development.

The genesis collector has NOT been switched to this unqualified source. Existing collateral qualification remains unchanged. A successful transport diagnostic alone cannot prove complete archive coverage or authorize genesis/live execution.

Six new config tests RED before implementation, GREEN afterward. Targeted suite: 37 passed, 0 failed/errors. Static audit AUDIT_OK; monetary transport hard-locked. Live flags and BTC V1 unchanged.

Future manual diagnostic, after local configuration: python -B .\analysis\diagnose_ctf_rpc.py --target-machine
Report: CTF_RPC_DIAGNOSTIC_<UTC>.json, no overwrite. Without configuration this command writes only the clean BLOCKED report and performs no network reads.
