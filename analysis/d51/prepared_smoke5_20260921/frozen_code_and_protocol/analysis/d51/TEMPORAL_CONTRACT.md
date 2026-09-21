# D5.1 temporal contract, before prospective data

Historical D5_DATA_QUALITY=FAIL is immutable. D5.1 is an opt-in new experiment.

- source_metadata: raw message timestamps retained without correction.
- wire_event_ts_ms: raw source timestamp of the last item in the incoming message, may regress across message types; not a composite book-state clock.
- UP/DOWN event_ts_ms: source timestamp of the last accepted book-changing message for that token, scoped to identity and connection generation. Equal allowed. Regressions rejected before mutation, including within a batch. Missing book update timestamp rejected.
- book_state_source_ts_ms and envelope event_ts_ms: max(UP source, DOWN source), only defined when both sides are timestamped. This is the latest component update time, NOT evidence that both sides are equally fresh. Always retain individual freshness.
- received_ts_ms: local wall-clock timestamp captured at incoming-message receipt; envelope receipt is separate from each side's last update receipt.
- available_ts_ms: persistence/processing availability, used for causal joins, existing store monotonic ordering retained and audited. Raw receipt must never be replaced or retrospectively shifted.
- New generation clears book state and requires both fresh authoritative books. No cross-generation time comparison or inherited book. Raw source regressions of wire metadata remain visible as diagnostics.
- No filtering of last_trade_price solely to hide envelope changes. No future source time is substituted for local receipt/availability.

Tests cover mixed message types, side timing differences, atomic batch rejection, missing timestamps and resets. Composite timestamp alone must never be used as freshness for both tokens.
