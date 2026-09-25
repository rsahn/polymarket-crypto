# Selected settlement cash evidence, not live readiness

The new pure reconciler validates Polygon 137 identity, exact collateral contract and wallet, pinned before/after balances, canonical block hashes supplied by the collector, successful receipt status, unique expected transactions and logs, log identity, freshness and uint256 Transfer amounts. Arithmetic stays in base units. A selected receipt net delta must exactly equal the balance delta. Self-transfers net to zero. No decimals/symbol assumption is introduced.

ERC20 event layout source: https://eips.ethereum.org/EIPS/eip-20 (Transfer). The installed polymarket-client 0.11.0 ClobTrade model exposes fee_rate_bps and transaction_hash, not an actual fee debit amount. No fee formula was guessed.

BoundExecutionStore.record_cash_observation records the public evidence and result atomically, tied to the original Genesis baseline, only for a locally closed recorded cycle. Unknown caller metadata is excluded. An expected-state check inside the write transaction prevents stale observations overwriting a concurrent new intent. This addresses a potential race introduced by asynchronously obtained evidence.

The result is CASH_DELTA_MATCHED with selected-receipt scope, not global completeness. Offsetting unexplained transfers cannot be ruled out from a net delta. Fees and PnL remain unknown, current_inventory_proven and submit_allowed stay false. Projection does not upgrade cash_reconciled from this bounded observation. No network collector of these receipt proofs has been integrated or qualified; inputs in tests are fixtures. A qualified collector must still establish receipt/header provenance, transaction-to-session attribution and effective fee information.

RED: new reconciler absent; integration RED: two missing-method failures. Final full guarded suite: 719 passed, 8 subtests passed, 3 deprecation warnings. Static boundary audit passed; SDK monetary attempts zero. Pattern scan covers changed source and test evidence; only the explicit fake redaction-test marker is allowlisted. No actual secret was loaded.

Genesis, BTC V1, fixed-C, freshness policy and monetary transport unchanged. No production session or network qualification run was started. This commit is not a completed live integration and does not remove the post-C completeness blocker.
