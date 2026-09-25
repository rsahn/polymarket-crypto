# Post-genesis snapshot generation and WS diagnostics

The 20260925_134112 report evaluated account observations 2759 ms after acquisition began.
Its generic WS error overwrote the actual exception; a historical close code/parser cause cannot be recovered from that artifact.

No 500 ms invariant is relaxed. Slow incremental CTF preparation and geoblock finish before the parallel account/order/trade/position reads start. Every original request-start timestamp remains intact. The inventory observation keeps its original chain timestamp (including the conservative block timestamp); sealing a generation never refreshes it.

The single acquisition generation requires exactly balance, orders, trades, positions and inventory, with matching generation IDs, complete pagination, ledger hash and a block-number/hash watermark. Missing, future, stale or mixed-generation evidence blocks reconciliation. This is a bounded observation window, not a claim of distributed transactional atomicity. The ledger hash is rechecked locally at the final gate. The live book is re-read after all awaited reads and local validation. Evaluation time is captured afterward. Shutdown occurs only after report capture. No reconnect is forced and no automatic retry is added. A newly connected generation must bootstrap both tokens with full snapshots; deltas cannot bootstrap them.

Safe WS diagnostics preserve the recognized parser rejection, age of rejected timestamp, close code/category, presence (not contents) of remote close text, last valid message metadata, per-token book ages and side availability, generation and bounded resync/disconnect transitions. Raw payloads, token IDs and arbitrary exception/close text are excluded.

Limit: sequential archive RPC evidence and the age of the latest block can exceed 500 ms. In that case GENERATION_STALE_500MS remains a real blocker, explicitly listing stale components. The timing change fixes delayed account observations, but does not prove that this provider can deliver an inventory watermark within 500 ms. No real-network PASS is claimed; another manual target-machine observation is required. No historical genesis scan, genesis mutation, signal edit, key loading or monetary operation was performed here.

Tests: RED captured 12 failures; an additional RED exposed evaluation time captured before local validation. GREEN includes synthetic full readiness while WS is live, cleanup afterward, stale/partial/mixed generations, two-token resync, parser-cause retention and secret-sentinel redaction. The offline readiness report deliberately blocks unavailable real sources.

Manual target command (existing process RPC configuration and existing protected L2 only):

    python -B .\analysis\qualify_post_genesis.py --target-machine

Return the newly created D6_POST_GENESIS_READINESS_<timestamp>.json. Never overwrite the previous artifact. The existing genesis is read; scans start after its reference block, then advance the verified cursor. If this incremental gap exceeds the existing bound, stop rather than launch historical discovery.
