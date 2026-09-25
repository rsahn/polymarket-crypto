# Final dependency DAG, before any change in this phase

Existing fixed-C is immutable in this phase. Operations:

| Operation | Required predecessor | Timestamp/proof | Invalidation |
|---|---|---|---|
| qualified finalized B, cursor->B | Genesis-bound cursor validation | original scan times, hash(B) | wrong chain, reorg, gap, partial RPC |
| select C once | anchor preparation | selected number/hash | C<B or cursor incoherent |
| parallel chain/header/code/log reads at C | C and validated cursor | original scan start, complete ranges | invalid response, omitted/overlapping range |
| balances at C | IDs decoded from all logs | actual response | unexplained event/balance => recovery |
| canonical scan check, seal C | all inventory reads | actual numeric header observations | hash mismatch |
| balance/orders/trades/positions parallel | seal C | original GET starts, parse finishes | partial page, failure, stale, mixed generation |
| numerical B/C rechecks parallel | ALL account reads complete | post-account canonicality observation | reorg |
| reconciliation/local checks | all required proofs | original times retained | incomplete/current scope unproven |
| book capture | live WS + local checks | source/receive preserved, new sample time separate | stale, disconnected, unsynced, invalid book |
| evaluate | captured book + proofs | actual evaluation clock | any gate false |
| durable cursor write | evaluation | persistence status only | failure reported; next run resumes older durable cursor |

DAG: prepare -> select C -> [chain/header/code/logs] -> balances -> scan check
-> seal C -> [balance/orders/trades/positions] -> [B recheck/C recheck]
-> reconcile -> sample existing WS -> evaluate -> persist.

The tempting edge removal (account || recheck) is NOT equivalent:
C is canonical at t=200, a recheck finishes at t=268, C reorganizes at t=280,
account finishes at t=291. Both concurrent branches succeeded but there is no
canonicality observation after account. The existing sequential contract would
observe the reorg. Without an independent reorg witness or block-pinned account
reads, the 298ms plan weakens the accepted fixed-C contract. Therefore reject it.

Historical checkpoint work is already outside the final window. A loaded
checkpoint is not a new observation: its timestamp cannot become the seal time.
Even perfect post-seal parallelism would not refresh the 796ms-old scan at seal
in the last run. No offline model may certify current inventory.

Before/after DAG in this phase: unchanged; instrumentation only. No new
performance result is claimed. The 1362ms target result is one sample, not p95.
