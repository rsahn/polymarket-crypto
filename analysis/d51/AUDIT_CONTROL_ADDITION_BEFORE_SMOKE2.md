# Additional audit controls before smoke 2

No threshold is relaxed and no existing report is replaced. The first smoke remains FAIL for its captured W32Time error under its frozen code, archived in smoke_20260921_092802/code_at_review.

A synthetic corrupt wire_event_ts_ms not matching preserved source_metadata was not detected by the first supplement. The failing test is preserved in wire_audit_regression_before_fix.log. The new supplement explicitly compares these fields and the payload envelope timestamp, validates stop markers/cleanup failures/local timestamps after stop, retains raw wire regressions as diagnostic counters, and records all transition/reconnect intervals even below the existing thresholds.

RECONNECT events include anchor-closure markers and retry markers. The completed smoke contains 6 markers but 3 actual retry attempts; INDEPENDENT_COMPLETION_CHECK.json preserves all six payloads. Future reports expose both metrics. This is counter clarification, not an acceptance exception.

The mixed last_trade_price -> price_change scenario is tested end-to-end through normalization, new synthetic SQLite, and the read-only supplement: raw wire regression retained; composite state and side clocks do not regress. Historical databases and timestamps remain unchanged.
