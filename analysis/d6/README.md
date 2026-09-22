# D6 — BTC → Polymarket lead/lag research

D6 measures whether BTC moves systematically precede executable Polymarket 5m/15m quote changes.

## Safety / research contract
- Offline analysis only. No real orders.
- D5.1 data-quality gates remain authoritative.
- No strategy optimization is authorized from the 22-minute smoke alone; a separate 24h+ quality-reviewed corpus is required before research conclusions.
- Use receive/source timestamps, never SQLite row order as a clock.
- Separate 5m and 15m markets.
- Report sample counts and distributions; do not infer profitability from latency alone.

## Phase D6.0
1. Validate the input D5.1 database/session.
2. Extract BTC and BOOK event timelines.
3. Build event-study windows around BTC moves.
4. Measure Polymarket response at fixed horizons.
5. Add depth/spread/executable-price analysis after timing correctness is proven.
