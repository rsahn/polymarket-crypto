# D6 stable-bound temporal contract — offline proposal, not production enabled

Scope: test an anchored inventory statement without weakening the current-inventory gate.

1. Select B once from eth_getBlockByNumber("finalized", false), chain 137, with the configured public RPC. Record B/hash(B), provider provenance (no URL secrets), request start/end and generation. No fixed confirmation depth invented. Provider support for this tag has NOT been qualified on the target.
2. Verify the saved cursor hash. If the cursor is ahead of finalized B, stop; do not rewind or restart Genesis. Otherwise scan exactly cursor+1..B, consecutive nonoverlapping successful ranges, all identified CTF event filters, and known/discovered asset balances at B. No missing or removed event accepted. Preserve original acquisition times, not seal time.
3. Read account, orders, trades, positions concurrently after the anchored scan; all required observations must be complete in the same generation. Re-read block B by NUMBER and compare hash(B). A changed hash invalidates the generation. A later latest head B+1 does not invalidate a statement explicitly scoped to B.
4. Every relevant acquisition timestamp must still satisfy 0 <= evaluation_time - observed_time <= 500 ms. This contract does not guarantee the existing serial RPC implementation can meet that limit. Block time, observation time and finalized selection time are different metadata; none may replace another.
5. An anchored statement is not current inventory: CLOB/Data API GETs are not pinned to B and credential-view orders/trades plus a possibly lagging indexer do not exclude external conditional transfers after B. Missing post-B evidence MUST keep current_inventory_proven=false and readiness blocked. No boolean configuration or account zero balances may bridge this gap.
6. Integration requires qualified finalized-tag semantics and a tested post-B observation protocol (fixed tail with its own canonical hash and explicit observation boundary, without omitted intervals), including current account/indexer limitations. The offline model intentionally never grants ready_for_arm or submit_allowed. It does not select blocks, call a network, update a ledger/cursor, or alter ProductionReadinessCheck.

Executable tests precede the model. Tests exercise B+1 stability, B reorg, cursor reorg, skipped/overlapping ranges, partial generation, original timestamp staleness, future timestamps and exact 500 ms boundary. The model consumes trusted *proof summaries*, not raw RPC; passing fixture booleans is not network verification.

References inspected 2026-09-25:
- https://docs.polygon.technology/pos/concepts/finality/finality (finalized tag and milestone finality).
- https://docs.polymarket.com/market-data/realtime-data (per-asset book and price_change schemas; no permission found to accept a same-token timestamp regression).

WS finding: BookStateSource already compares against self.books.get(token); equal timestamps and independent-token ordering pass unchanged. The historical report establishes a 1 ms regression but does not retain the rejected type/token. New diagnostics capture those before invalidation; acceptance remains unchanged. No new qualification is authorized by this patch because both root causes are not yet resolved.
