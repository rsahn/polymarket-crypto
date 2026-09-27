# BTC V1 prospective protocol — closure delta, 2026-09-27

**BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED**

Requested baseline: closure assessment983/79. Actual starting HEADfa8f4f709f371b72e537ec49400dab807e010c2a already contains the subsequent qualification993/88. These old proofs are preserved. Only four offline diagnostic/recovery source files and this new evidence directory are added. No old smoke, economic experiment or completed exhaustive audit is rerun.

| # | Requested output | Result |
|---|---|---|
|1|DEPTH_REUSE_EMPIRICAL_AUDIT|15 opportunities,0 actual entry states identifiable,15 unidentifiable. Reuse/new-state/same-token/overlap counts UNKNOWN. Historical aggregate fill quantities retained where available; requested quantity unknown, notional25. Nominal entry_due=signal+250 is explicitly not actual entry_observation. [Rows](DEPTH_REUSE_EMPIRICAL_AUDIT.json).|
|2|DEPTH_MODEL|DEPTH_MODEL_NOT_IDENTIFIABLE_FROM_CURRENT_EVIDENCE.|
|3|Causal justification|Distinct local event+market+generation+token IDs, independent depth fingerprints. Technical prefix:2000 token observations,1894 proven new token book events,412 same-content/new events,106 without proof of new token event. This proves observable identity differences, not counterfactual replenishment or actual V1 entry selection. [Identities](BOOK_IDENTITIES.json).|
|4|REAL_V1_BINDING|REAL_V1_BINDING_NOT_QUALIFIED, because depth semantics and actual V1 entry bindings are unidentified.|
|5|OBSERVABILITY_V1_R1|Unchanged, unadopted. ASTceaa1974edd442eedb94c038940cdcd0a8e987139b58a55316a8cc855680d6ef. No extra hook implemented before depth qualification.|
|6|Differential equivalence|ECONOMIC_BEHAVIOR_IDENTICAL=true **on existing synthetic differential fixtures only**: normal, partial exit, NO_EXIT_DEPTH, rotation and signal ordering/logical times. Prior [proof](../blockers_20260926/DIFFERENTIAL.json) preserved; related tests remain in full suite. Real-world scheduling and book completeness not proven.|
|7|Authoritative fee field|Standard account trade/maker trade:fee_rate_bps is a rate. BuilderTrade exposes fee/fee_usdc, but attribution, exact platform-fee meaning and final applicability to V1 are unproven. No exchange fill/charged amount exists for a simulated no-order fill. [Static SDK fields and sources](FEE_FIELDS.json).|
|8|Exact local fee model|EXACT_LOCAL_FEE_MODEL_PROVEN not established; boundary rounding, aggregation and partial allocation remain unspecified for applicable path.|
|9|Conservative bound|CONSERVATIVE_FEE_UPPER_BOUND_PROVEN not established; prior conditional sum(raw)+N*u and aggregate-rounding counterexample preserved. No zero fallback.|
|10|Final fee qualification|MARKET_FEE_UNQUALIFIED.|
|11|JOURNAL_168H_UPPER_BOUND|null; JOURNAL_168H_BOUND_UNPROVEN. No maxbytes/event, maxevents/opportunity, nonopportunity cadence or checkpoint-event bound in current schema.|
|12|CHECKPOINT_168H_UPPER_BOUND|null; CHECKPOINT_168H_BOUND_UNPROVEN. No economic checkpoint format/cadence/count/size contract. New scratch DB is not a checkpoint.|
|13|Replay architecture|New offline disk histories/maps/sets with unchanged economic transitions; validated streaming input. Explicit disable of live observe. No history eviction or latest-only book shortcut. RAM still depends on largest record/depth and active positions/marks; no unconditional RSS bound. [Architecture](REPLAY_ARCHITECTURE.md).|
|14|Replay equivalence|PASS for complete ledger fixture prefixes, restart from source, two tokens/rotation, delayed fee annotations, same-content books; exact canonical economic/accounting/depth state, identity, final hash and sequence. Invalid fees/depth/duplicates/torn sources reject. REPLAY_CAPACITY_UNQUALIFIED remains at protocol level.|
|15|Stress metrics|100000 MARKs:24.131s,4144.042events/s,peak34668544bytes.60000 events including20000 books/trade states:27.088s,2215.030events/s,cumulative peak34672640bytes. Economic scratch51204096/44191744bytes plus IDs2207744/1323008bytes. Samples/source hashes [here](STRESS.json). Initial dependency/generator failures preserved; no strategy performance inference.|
|16|archive_168h|153994953187bytes; existing lossless smoke proof retained, no rerun.|
|17|QUALIFIED_REQUIRED_SPACE|null. Existing minimum369587887649bytes; journal/checkpoint/scratch bounds absent.|
|18|Free space|45969313792 bytes at 2026-09-27T07:32:01.562516+00:00.|
|19|Additional bytes required|Exact=null; minimum deficit323618573857 bytes. Not STORAGE_SPACE_ONLY_BLOCKER. [Capacity](CAPACITY.json).|
|20|Targeted tests|21PASS/33subtests/0FAIL. [Log](TARGETED.log).|
|21|Full suite|1001PASS/98subtests/0FAIL,106.03s;3 existing DuckDB deprecation warnings.111 files. [Log](FULL_SUITE.log), [hashes](VALIDATION.json).|
|22|Audit/leak scan|PASS after manifest/source/old-evidence/log checks and scoped secret-pattern scan; [AUDIT.json](AUDIT.json).|
|23|BTC V1 hashes|paper_live.py5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364; runnera9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405. Unchanged.|
|24|Criteria hash|869a386b9112a572247e3fb61ffbf4a27afb20493a791929e72f52bc0d9cd06a. Unchanged, including72/48/48.|
|25|D6 unchanged|No inventory,500ms,bootstrap,post-C,WS,risk or readiness modification. Genesis5365085da95cecb49fa4c922b890e9803ef223fdefef541505c2dc5a3de7814f unchanged.|
|26|Flags|REAL_ORDERS_ENABLED=false;LIVE_EXECUTION_ARMED=false;submit_allowed=false.|
|27|Monetary SDK attempts|0;16 guarded SDK methods in tests;0 external test connections attempted. Stress creates no SDK client and rejects socket connects. No account call, signature, cancel or allowance update.|
|28|Commit SHA|Dedicated local commit after GREEN/audit/leak PASS; exact SHA delivered in final response (not self-referential report content).|
|29|Push|PUSH_PENDING_AUTHORIZATION. No push attempted. Earlier auto-review rejected public publication of code/evidence without specific authorization for that public payload.|
|30|Verdict|BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED.|
|31|Remaining blockers only|1.Depth semantics+real V1 binding.2.Market fees.3.Journal/checkpoint/scratch/storage bounds, protocol replay capacity and insufficient disk.|
|32|Startup command|None:BLOCKED. No TRAIN/VALIDATION/OOS/PAPER/live run.|

## Depth: observations versus hypothetical consumption

[MODEL_COMPARISON.json](MODEL_COMPARISON.json) evaluates the three conventions algebraically at asks0.5×50 and FIXED25. On the same state twice,A fills50+50,B and C50+0. On an identified new event with identical depth,A and C50+50,B50+0. Time alone leaves B/C50+0. These are synthetic contract implications, never observed opportunity frequencies or model selection. No PnL, ROI or win rate is used. B is the existing persistent BookTape convention, including increases by observed positive level deltas.

Full-book token identity explicitly establishes a new observed event even if content and source metadata repeat. In price_change, changed token metadata proves that token was updated; stripped aggregate metadata cannot prove an identical-content/identical-metadata update to a particular token. Last-trade and opposite-token reemissions do not by themselves prove a new token book. Unknown cases remain unknown. Next-state pointers are retrospective inspection aids, never inputs to a decision.

The technical prefix is reused to derive a new identity relation, not to repeat normalization benchmarks or certify historical entries. None of the15 historical opportunities has the actual entry callback clock/book reference. NominalT+250 brackets cannot repair this gap. Even proving a new external event does not show which external orders would remain after fills never actually placed. C is a possible internal simulation contract; it is not demonstrated as the real V1 semantics. Applying persistent consumption on same-state reuse can differ from original V1. No C state machine is adopted and no hook is presented as resolving an economic mismatch.

## Fee evidence limited to remaining unknowns

The [official order/trade documentation](https://docs.polymarket.com/trading/manage-orders) exposes rate fields on standard account trades and fee/fee_usdc on builder-attributed matched trades. Existence of those builder fields does not prove they equal the complete platform fee needed here. The [builder fee documentation](https://docs.polymarket.com/programs/builders/fees) states builder and platform fees are additive and computed at match time. No signed/authenticated query is needed or made for this inspection. An authoritative final amount would require exact fill identity, units, fee scope, finality and once-only allocation. It could describe a real confirmed fill; it cannot supply an exchange debit for a synthetic prospective fill. No fallback or unqualified field is wired into the ledger.

The existing0.07/exponent1/takerOnly market evidence and exact-rounding unknowns remain intact. No repeated market API audit, real order, account reconciliation or settlement experiment is performed.
