# Bounded CTF segment policy V1

Target evidence GENESIS_READINESS_20260925_120304_984090 confirms the sole discovery refusal: 90,564 blocks, 94,331,195 through 94,421,758 inclusive, exceed the 50,000-block scan cap. No logs/authenticated reads were issued; no genesis exists from this observation.

The optional --chunked-ctf policy constructs a contiguous plan BEFORE event reads. Every segment remains <=50,000 blocks and the underlying RPC windows remain <=500. The whole range is capped at 200,000 blocks, all discovered/known IDs at 10,000. The initial anchor is checked against the last initial segment. A single moving-head catch-up of <=5,000 blocks re-reads balances of every discovered ID at one recent reference block, then all segment hashes are rechecked. No retry loop, gap truncation, fabricated IDs or global-history claim. If head is unchanged, its single block is rescanned; event count explicitly includes that possible overlap.

The manifest with from/to/hash/kind and canonical SHA256 is retained in the genesis snapshot and redacted success report. Partial failures include the completed manifest and safe reason. A failed segment, reorg, budget excess or unavailable evidence refuses genesis. Nonzero final balances flow to the existing RECOVERY_REQUIRED check before L2 loading. All original index/account/ledger gates remain required. Existing CTF counterfactual-predeployment and archive trust limitations remain explicit.

Command (normal target PowerShell, repository root):
python -B .\analysis\qualify_genesis.py --target-machine --chunked-ctf
Return only the new timestamped GENESIS_READINESS_*.json. The report and genesis ledger refuse overwrite. This invocation may create genesis only after the existing acceptance predicates pass; never an order.

Validation: four initial feature tests RED before implementation (missing function). Eight new segment tests GREEN. Backend suite: 388 passed, 8 subtests passed, 0 failed/errors in 20.35s. Static audit AUDIT_OK, monetary_methods_hard_locked=true. No production RPC/authenticated network was executed during this work. BTC V1, credentials, flags and monetary transport unchanged. Neither book connectivity nor live readiness is inferred from discovery.
