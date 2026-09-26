# Three historical failures — provenance and treatment

Classification: C. OPTIONAL_CANDIDATE_NOT_ADOPTED.
Secondary defect: the archived candidate's tests imported the production Store.

Exact test names:
- DepthCacheTests.test_bytes_exact_for_both_schemas_mutation_and_signed_zero
- DepthCacheTests.test_capacity_eviction_and_clear
- DepthCacheTests.test_nonfinite_still_rejected_and_not_cached

First reachable commit containing their archived path:
4b486fa7240269eaa6cdf2b0e5e92184f3a45f2a
2026-09-21T16:29:43+02:00
D5.1: improve realtime collector and async writer architecture

Subsequent commit touching that path:
675ffa4d47fa8a2e70a8a74add4ba531c0f1d4a7
2026-09-21T17:49:51+02:00
D5.1: optimize realtime collector and async writer

git log --all -S 'def pack_depth' -- backend/app/d5/store.py returned no commit.
The production Store in the introducing commit also had no pack_depth.
The preserved store_candidate.py DOES define pack_depth at line 93.
It is an exact-byte cache of capacity 256 and clears it on close.

The existing DECISION.md, already committed with the archive, says it was not
adopted: exact persistence equivalence passed but the recorded single run measured
1683 frames/s baseline versus 1570 for the candidate. That historical decision
is retained; this mission did not rerun a performance benchmark.

Treatment: tests load the preserved candidate source in a temporary fixture
using its original app.d5 package context. The two schema files are copied into
that temporary fixture. git diff between the introducing commit and HEAD for
schema.sql/schema_v2.sql is empty. No candidate code was changed or adopted.
All three assertions execute; no exclusion, skip or xfail was introduced.
Production Store is unchanged. The temporary databases are newly created.

There is no dependency from prospective_v1 to this candidate and no requirement
for BTC V1 to implement pack_depth. The failures were not introduced by 3b4a296;
a broader test inventory exposed the erroneous archived-test import.
