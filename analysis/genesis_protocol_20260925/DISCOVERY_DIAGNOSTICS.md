# Genesis discovery diagnostic correction

The target report GENESIS_READINESS_20260925_115629_677741 showed 33 successful public RPC reads, no event reads and no authenticated reads. It does not establish why discovery stopped. No genesis was created.

The collector now preserves internally selected discovery failure codes and validated public block boundaries. A range exceeding the existing 50,000-block limit reports from_block, to_block, block_count and maximum_blocks. The bound remains unchanged. Provider exception messages are never copied to the report. No network was run during this correction.

Validation: two regression tests failed on the original implementation after configuring PYTHONPATH (an earlier invocation failed collection because app was not on the path). After correction, four new diagnostic tests and fifteen existing genesis tests passed: 19 passed, 0 failed. Collector fixtures assert neither L2 loading nor ledger creation occurs after discovery refusal. Static audit: AUDIT_OK, monetary_methods_hard_locked=true. BTC V1 and flags unchanged.

Manual target rerun: python -B .\analysis\qualify_genesis.py --target-machine
Return the newly timestamped GENESIS_READINESS_*.json. Existing reports are not overwritten.
