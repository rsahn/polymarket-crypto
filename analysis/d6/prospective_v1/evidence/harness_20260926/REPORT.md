# BTC V1 prospective protocol — final technical report

**BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED**

No collection was started. No real TRAIN, VALIDATION or OOS was opened.
No edge is claimed. Full-suite GREEN is a software result, not economic validation.

1. **Root cause of the three old failures:** OPTIONAL_CANDIDATE_NOT_ADOPTED.
   Archived tests imported production Store although pack_depth exists only in
   the preserved candidate. First commit 4b486fa7240269eaa6cdf2b0e5e92184f3a45f2a,
   2026-09-21 16:29:43 +02:00. Details and exact names: HISTORICAL_FAILURES.md.
2. **Treatment:** run all three tests against the preserved candidate loaded in
   an isolated temporary fixture. Zero skips/xfails. No production Store change.
3. **Fee qualification:** per-market/token deterministic records are implemented.
   Official public BTC 5m market 4961058 confirms enabled, rate .07, exponent 1,
   takerOnly=true. Exact match rounding/aggregation remains unproven.
   Both tokens remain MARKET_FEE_UNQUALIFIED. No fee defaults to zero.
4. **Causal adapter:** implemented and ledger-integrated on complete synthetic
   observations. NOT connected to real V1. Two executable counterexamples prove
   missing entry observations on NO_EXIT_DEPTH and repeated reuse of unchanged
   depth. Exact passive real binding is not proven and remains blocked.
5. **Durable journal:** mandatory fields, canonical hash chain, strict sequence,
   identity/partition/clock checks, OS single-writer lock, flush/fsync, poisoned
   writes, fail-closed torn recovery. Actual subprocess crash/recovery tested.
6. **Ledger integration:** transactional validate → fsync → apply; recovery replays
   depth and ledger. Fees, reservations, partial fills, residuals and settlement
   tested. Unknown<<1rks and outstanding positions are retained and prevent PASS.
   Real causal marks and full observed fills remain unavailable.
7. **Evaluator:** integrated with the sealed loader and immutable criteria file;
   deterministic 6h/12h bootstrap, 10,000 replicates, fixed seed, empty hours
   retained. Synthetic PASS, FAIL and INCONCLUSIVE tested. No economic real data
   evaluated. Liquidity attribution is explicitly unqualified; full real reporting
   cannot be completed without the missing observation contract.
8. **Sealed partitions:** synthetic loader verifies manifest/source/file hashes,
   closed intervals, membership, upstream result hashes and freezes.
   Real-loader entry is fenced with REAL_V1_BINDING_NOT_QUALIFIED.
9. **OOS first access:** exclusive fsynced marker precedes exposure; crash consumes
   access, second load is rejected. Upstream TRAIN and VALIDATION PASS required.
   Only synthetic markers have been created in temporary test directories.
10. **Storage preflight:** observed 4,800,663,552 bytes / 1320.0542836000677 seconds
    projects 2,199,486,303,194 bytes across 168h for that collector workload.
    Planning reserve: 5,278,767,127,666 bytes before separately qualified
    journal/checkpoint allowance. Free at check: 47,996,882,944 bytes.
    This is an observed-workload extrapolation with an explicit engineering
    margin, not a proven future peak or exact isolated-5m estimate.
    DISK_CAPACITY_UNPROVEN and DISK_SPACE_INSUFFICIENT remain.
11. **Boundaries:** T0 UNBOUND, no real manifest. Planning function is implemented:
    only after all gates pass, UTC 5m boundary at least 10 minutes ahead;
    72/48/48h unchanged, embargo60s, whole-market purge unchanged.
12. **Prospective tests:** original25 preserved; 53 additional tests plus3
    subtests. Three archived candidate tests also pass. Initial RED was a
    missing journal module; targeted final tests are GREEN.
13. **Full suite:** 107 test files, 962 PASS, 61 subtests PASS, 0 FAIL.
    Three existing DuckDB deprecation warnings. Sources unchanged during run.
    FULL_SUITE.log and VALIDATION.json preserve the evidence and hashes.
14. **Audit:** PASS for the scoped offline components and safe BLOCKED behavior.
    This is NOT a production-readiness audit PASS. Runtime modules import no
    collector, monetary SDK, scheduler or HTTP request client.
15. **Leak scan:** PASS on targeted credential/private-key patterns for new files
    and prior commit review. Public condition/token IDs and file hashes are
    recorded as public evidence, not secrets. No private-key file was read.
16. **BTC V1 hashes, before = after:**
    - paper_live.py: 5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364
    - run_d6_paper_live.py: a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405
    - Genesis: 5365085da95cecb49fa4c922b890e9803ef223fdefef541505c2dc5a3de7814f
    - criteria.json unchanged against the preparation baseline.
17. **Files:** only the archived candidate test import/fixture is modified.
    New files: journal.py, engine.py, sealed.py, evaluator.py, preflight.py,
    test_harness.py, INTEGRATION_CONTRACT.md and this new evidence directory.
    No old evidence, old database, strategy, runner or backend runtime file edited.
18. **Commits:** immutable parent 3b4a296c2e603bfd513b3c70a6069cd832f6789d.
    This delivery is committed separately above it, with an accurate message
    retaining BLOCKED status. Exact delivery SHA is in the final Git receipt.
19. **Push:** authorized conditionally after full-suite GREEN and scoped
    audit/leak/scope checks. Those checks passed. Effective remote verification,
    rather than intent, is reported in the final Git receipt.
20. **D6 technical state:** unchanged; SYSTEM_READY=false,
    current_inventory_proven=false. Genesis/post-C/CLOB/WS/risk/semantic untouched.
21. **Flags:** REAL_ORDERS_ENABLED=false, LIVE_EXECUTION_ARMED=false,
    submit_allowed=false.
22. **Monetary SDK attempts:** 0; 16 SDK methods guarded. Existing transport lock
    tests account for3 calls to locked production wrappers, never SDK sends.
23. **Exact result:** BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED.
    Primary blockers: incompatible complete passive V1 observation/depth contract;
    exact exchange fees; insufficient/unqualified storage. Production seal,
    current clock evidence and absolute boundaries are consequently not released.
24. **Launch command:** deliberately NOT supplied because READY is false.

## Decision needed before the real binding can be completed

With both V1 file hashes frozen, the missing entry callback cannot simply be added.
Allowing a changed observation hook or a different counterfactual fill policy
would need an explicit revised, versioned contract; this report does not make
that change. Storage also needs an adequate destination or an approved,
lossless and measured reduction plan. These are genuine unresolved constraints,
not a request to approve a run.

Read INTEGRATION_CONTRACT.md for the precise implementation limits, including
in-memory replay/state-copy scalability that has not been qualified for a week.
