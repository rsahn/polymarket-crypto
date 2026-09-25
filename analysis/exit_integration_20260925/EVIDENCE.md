# D6 exit integration, offline only

The execution controller used a price supplied before the hold, despite an existing current-book exit policy. It now rereads authenticated account evidence after the hold, checks held quantity, samples the gate, and uses plan_exit with explicit slippage and real bid depth. Partial depth never closes the residual position. Missing/invalid/stale exit evidence fails closed. No transport is unlocked.

RED: 7 new regressions failed, 21 existing tests passed.
GREEN: 28 controller tests passed.
Full guarded suite: 666 passed, 8 subtests passed, 3 deprecation warnings.
Static boundary audit passed. SDK monetary attempts: 0. Flags false in harness.

Genesis hash, BTC V1, fixed-C contract, and monetary transport unchanged (INVARIANTS.json). Pattern leak scan covers changed source and test logs only, not global history. No secrets were loaded.

Remaining: current_inventory_proven is still false by the existing post-C contract. No available common account/indexer completeness watermark was added or invented. This patch does not connect a production account source or an exit book source to a live runner. A live runner must supply exit_book and an explicit max_exit_slippage_bps. The pre-hold exit_price argument remains compatibility-only and cannot determine an execution price.

The user-approved 1300ms policy has not yet been applied; existing 500ms checks remain. No production or network validation claimed; no live launch command is delivered.
