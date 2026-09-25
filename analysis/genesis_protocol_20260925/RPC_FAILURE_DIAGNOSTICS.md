# First eth_getLogs failure: sanitized RPC diagnostics

Actual target GENESIS_READINESS_20260925_120857_642668: first segment failed, manifest empty. Calls 1-36 PASS; call 37 eth_getLogs FAILED. No authenticated GET and no genesis. This establishes a public RPC read failure, not its underlying HTTP/JSON-RPC cause. No provider restriction is asserted without evidence.

PublicRPC now retains HTTP status, validated numeric JSON-RPC error code, safe category and public requested block range. Classification from provider message patterns is explicitly labelled as not independently verified. Raw provider text/error.data, headers, URLs from exceptions, wallet/topics and full response are never copied. Response ID/version validation precedes error classification. Fixed provider, allowlist, window budgets and failure behavior unchanged. No retry or alternate provider.

Six regression cases failed before correction; eight new diagnostic cases pass afterward. Targeted transport/collateral/genesis suite: 51 passed, 0 failed/errors. Static boundary audit: AUDIT_OK, monetary_methods_hard_locked=true. No actual RPC/authenticated network run, private key, credential recovery, or monetary operation during this correction. BTC V1 and live flags unchanged. This is diagnostic instrumentation, not a fix for an as-yet unidentified provider failure.

Manual target command:
python -B .\analysis\qualify_genesis.py --target-machine --chunked-ctf
Return only new timestamped GENESIS_READINESS_*.json. No old report overwritten.
