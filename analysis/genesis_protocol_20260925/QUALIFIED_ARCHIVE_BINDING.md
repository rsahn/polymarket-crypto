# Explicit use of target-qualified archive RPC for manual genesis

User supplied CTF_RPC_DIAGNOSTIC_20260925_123523_229326: chain137, historical CTF code and ten-block logs all HTTP200; zero rows. This proves only that sample, not empty global inventory or complete archive coverage.

New opt-in --archive-rpc on the chunked manual collector uses POLYGON_ARCHIVE_RPC_URL without dRPC fallback and emits only the variable name as provenance. CTF RPC windows are 10 blocks, matching the qualified range. Internal discovery segments remain <=50,000; total <=200,000 and catch-up <=5,000, all existing hashes/freshness/account/ledger guards unchanged. Roughly 9,000 log reads for a 90,000-block span; may take substantial time. Existing transport rejects redirects and nonallowlisted methods. No secret URL recorded. Configuration must remain in the same target shell used for qualification.

Manual command: python -B .\analysis\qualify_genesis.py --target-machine --chunked-ctf --archive-rpc
Not run during development. Existing L2 may be read only after successful public discovery; no private key, recovery, L1 signature or transaction. Genesis can be created only by existing acceptance predicates. Flags false, monetary transport locked, BTC V1 unchanged.

Three binding regressions RED before implementation. Targeted suite:70 passed,0 failed/errors. Static audit AUDIT_OK. No production network or genesis run performed here.
