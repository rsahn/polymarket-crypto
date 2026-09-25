# Minimal archive RPC qualification

The isolated diagnostic now verifies exactly chainId 137, nonempty CTF contract code at block 94331195, and one incoming CTF eth_getLogs filter over ten blocks 94331195..94331204. Missing configuration, wrong chain, unavailable historical code or any RPC error => BLOCKED, no fallback. Success is PASS_READ_ONLY_RPC, explicitly limited to the tested historical block/range, not proof of global archive completeness. No L2, key, transaction or genesis operation.

Configure POLYGON_ARCHIVE_RPC_URL only in the manual target PowerShell process. Use Read-Host -AsSecureString and convert to the process environment variable in memory; never paste a literal endpoint with a provider key into command history. No dotenv is loaded. The value expires when this shell closes (or remove Env:POLYGON_ARCHIVE_RPC_URL). It must be an HTTPS Polygon Mainnet endpoint supplied by the chosen provider; no key is created by this project.

Qualification command: python -B .\analysis\diagnose_ctf_rpc.py --target-machine
Return only the timestamped CTF_RPC_DIAGNOSTIC_*.json. Keep the same shell for later work, but do not launch genesis. The genesis collector has not yet been switched to this new provider; a PASS report is required before that separate step.

Four regression assertions failed before implementation; 40 targeted tests pass afterward, 0 failures/errors. Static audit AUDIT_OK. No actual network qualification was executed during development. Flags false; BTC V1 and monetary transport unchanged.
