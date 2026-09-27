# Depth semantics — evidence, not model selection

**DEPTH_MODEL_NOT_IDENTIFIABLE_FROM_CURRENT_EVIDENCE**

Scope: 13 dated historical PAPER reports under analysis/d6/paper_live, deduplicated by signal timestamp and direction; 15 unique signals, 12 fixed_25 aggregate fills and 3 skips. Five existing base DBs under data/d6 inspected read-only for session coverage. No new economic replay/partition or repair of loose WAL/SHM was attempted. Source stat checks and report hashes are in DEPTH_REUSE_EMPIRICAL_AUDIT.json.

None of these callbacks records the actual entry decision clock, selected book identity, per-level consumption or exit decision clock. One opportunity has a DB/slug match permitting nominal T+250 brackets; that diagnostic does NOT bind a book to execution. Other observations remain unknown. Legacy reports include exit_price rather than current runner exit_vwap: current V1 source is not retroactively assigned to them. An existing NO-SUBMIT lifecycle replay at analysis/d6_replay_validation is a simulated fill-ratio exercise, not book-selection evidence. The compact-window extractor exists as code; no compact/window DB was found under analysis/data. Its schema drops token/source timestamp/generation/sequence/hash and persistence availability; even such an extract alone would not recover actual scheduler decision clocks.

Therefore all actual-entry same-book counts/rates, overlaps, update-between-opportunities and A/B classification are UNKNOWN (15 cases C). Unknown is not zero reuse. Signal spacing alone cannot prove lifecycle overlap or absence of overlap. Missing observations cannot be reconstructed from nominal sleeps or a future book.

## Proven local pipeline behavior

backend/app/collectors/polymarket_ws.py:
- full-book initializes/replaces displayed sides for the addressed token;
- price_change requires a full book in the connection; size replaces the level's quantity (not an increment), size<=0 removes it;
- source timestamp/hash/optional sequence/receive timestamp update for addressed tokens;
- a composite output can include an unchanged opposite-token side; non-book messages can also emit the existing depth;
- connection generation and persistent generation identify separate local contexts; neither is a queue-order identity.

backend/app/d5/store.py writes every accepted BOOK envelope with event_id (local DB order), envelope/source/receive/persistence-availability times and per-token side metadata and complete levels. Local event_id is NOT an exchange update sequence. The quote callback is delivered separately from persistence; persisted available_ts is not demonstrated as V1's actual callback availability/selection clock.

The fixed first 1000 BOOK envelopes in the already reviewed smoke show 2000 token observations: 95 identical token-state reemissions, 1903 changed states, 482 transitions with identical depth values; exchange sequence absent in all 2000. Wire metadata types: 952 price_change, 34 single book, one book pair, 13 last_trade_price. These are technical pipeline observations, NOT 2000 economic opportunities. Full examples include token, timestamps, hashes, generation, local ID and bids/asks in PIPELINE_OBSERVATIONS.json.

A fresh state message shows a displayed state; it does not identify which external orders survived, were consumed, replaced or hidden between observations. Our simulated fills were never sent to the exchange. Hence neither unchanged metadata nor a new hash can by itself prove the counterfactual remaining liquidity after our hypothetical trade. Do not infer no external replenishment from silence, and do not replenish merely by time.

## Offline model impact

Actual opportunities affected, fills affected, quantity and PnL differences: UNKNOWN for these 15 signals. Exact chosen books/lifetimes are missing. Model C is not demonstrated admissible, so it was not evaluated. The previously sealed synthetic counterexample still gives A=50+50 and B=50+0 shares at 0.5; it proves divergence of conventions, not their frequency in the real run, and is not used to choose a profitable model.

The existing integration contract calls BookTape a conservative counterfactual convention. It is internally specified but not empirically established as venue queue truth. No model is adopted or modified.

**REAL_V1_BINDING_BLOCKED_BY_UNIDENTIFIED_DEPTH_SEMANTICS**.
OBSERVABILITY_V1_R1 remains versioned, unadopted and unchanged. It exposes more snapshots/fill observations; its old differential fixtures remain valid. Those hooks alone cannot identify external queue replenishment or resolve the conflicting economic contract. No real binding is claimed.
