# HTTP 400 body diagnostics / isolated reproduction

Target report GENESIS_READINESS_20260925_121348_416804 demonstrates HTTP 400 on eth_getLogs over 94331195..94331694. It does not yet demonstrate an invalid filter, plan restriction or range restriction. No genesis or authenticated GET occurred.

Correction: urllib.HTTPError bodies are read at most 16,385 bytes, rejected over 16,384, and classified in memory. Only fixed categories, bounded numeric code and response-ID-match boolean survive. No message, error.data, headers, raw body, wallet, signature or key is logged. Non-JSON, oversized, unavailable or mismatched-ID bodies remain failures. Provider classifications are labelled unverified. No success or fallback can arise from HTTP 400.

The isolated analysis/diagnose_ctf_rpc.py verifies chain 137 then issues exactly one unchanged public eth_getLogs request for the failing 500-block range through the same pinned RPC. No L2 reader, private key, account GET, retry, inventory assertion or genesis write. New CTF_RPC_DIAGNOSTIC_<UTC>.json uses exclusive publication.

Validation: four HTTP body regressions RED before correction; all passed after. Total targeted suite: 58 passed, 0 failed/errors. Static audit AUDIT_OK. No production network executed during development. Flags, monetary transport and BTC V1 unchanged.

Manual command from repository root:
python -B .\analysis\diagnose_ctf_rpc.py --target-machine
Return only CTF_RPC_DIAGNOSTIC_<UTC>.json.
