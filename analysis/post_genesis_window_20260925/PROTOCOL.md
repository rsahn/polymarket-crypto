# D6 post-genesis live observation window

Scope only: D6_POST_GENESIS_READINESS. No D5, shadow collection, paper, risk or signal change.

Inventory: the incremental scan remains unchanged and retains its original observation timestamp. After catch-up, a NEW eth_getBlockByNumber(latest) runs concurrently with balance/orders/trades/positions. Only an exact number/hash match with the fully scanned CTF watermark can attest that the canonical state is still that scanned state at this new remote observation. observed_ms is the actual new request START, not receipt time or evaluation time. scan_observed_ms and head_block_timestamp_ms remain separate and unchanged. This is a new current-state witness, not relabeling old scan evidence. Pending transactions and unindexed/off-chain activity are not covered. The existing scoped coverage limitations remain.

If the head advanced, discard the entire candidate generation, advance only the post-genesis delta and reacquire all four GETs and the head witness. Maximum three attempts; no fallback. Reorg, timeout, incomplete data and a witness older than 500 ms block readiness. A same-head witness cannot make an old block timestamp newer; block age remains reported explicitly. The 500 ms gate applies to this actual new remote observation. No longer using block creation time as the timestamp of a new latest-state read.

WS: connected reflects the socket lifetime; synchronized reflects both token snapshots; fresh is a distinct <=500 ms check. EMPTY_BOOK and CROSSED_BOOK are separate exact errors. Local stale/empty/crossed events invalidate both books without pretending the TCP connection closed. Run remains connected, awaiting two full snapshots; deltas cannot bootstrap resync. No forced reconnect. Actual disconnect still clears books. Expiry remains fail-closed.

Diagnostics include original wire timestamp, last valid book timestamp, per-token counts and best prices, generation, exact invalidation reason, connection/resync transitions and sanitized close metadata. No raw payload or arbitrary exception text.

Validation: 7 RED regression failures before changes. New tests exercise exact causes, stale-wire invalidation while connected, full resync, a genuine latest-head RPC witness, immutable scan timestamps, new-head retry of the whole generation, reorg and timeout. Earlier tests now assert invalid availability rather than a fictitious socket disconnect. Fake sockets close explicitly after a recoverable parser error.

Network qualification still needs the target PowerShell: RPC configuration is absent in this Codex process. No credentials loaded or network called here. OFFLINE_READINESS is explicitly not network qualification. Run locally with the existing RPC/L2 setup:

    python -B .\analysis\qualify_post_genesis.py --target-machine

Return the new timestamped D6_POST_GENESIS_READINESS JSON. Genesis and BTC V1 remain unchanged; flags false; submit_allowed false; monetary transport hard locked.
