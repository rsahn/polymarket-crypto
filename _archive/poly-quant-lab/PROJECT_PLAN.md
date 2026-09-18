# Project plan

## Phase 0 — Scaffold (done)
- Async Python service
- SQLite schema
- Binance public collector
- Strategy primitives S1/S2/S3/S4
- Paper executor skeleton
- Benchmark configuration

## Phase 1 — Data integrity
1. Polymarket market discovery for active BTC 5m/15m windows.
2. Polymarket CLOB WebSocket order-book collector.
3. Persist source timestamps + receive timestamps.
4. Reconnection, sequence-gap detection, health metrics.
5. Snapshot/replay tests.

**Gate:** 24h uninterrupted collection with no unexplained gaps.

## Phase 2 — Benchmark reconstruction
- Fetch public activity for Bonereaper, BoneOhio, lkkdnfa.
- Normalize fills by market/window/outcome.
- Reconstruct inventory path and paired vs directional exposure.
- Compute time-to-hedge, pair-cost distributions, entry time, sizing distributions.

## Phase 3 — Strategy research
- S1 Temporal pairing with explicit unhedged-leg accounting.
- S2 Cross-market spread model and rolling Z-score.
- S3 BTC impulse -> Polymarket repricing lag.
- S4 SPRT with probabilities calibrated from historical observations (not arbitrary +3/-3 assumptions).

## Phase 4 — Realistic paper execution
- Consume visible depth, not midpoint.
- Partial fills.
- Fee/slippage model.
- Capital constraints.
- Inventory limits and kill switch.
- Market settlement and realized PnL.

## Phase 5 — Dashboard
Trading-desk UI:
- PAPER badge / connection health
- BTC live chart
- UP/DOWN order books
- S1-S4 signal cards
- PnL / expectancy / profit factor / max drawdown
- paired inventory / directional exposure / hedge rate
- expected edge vs realized edge
- event log and paper trades

## Phase 6 — Validation
- Train/validation/out-of-sample separation.
- Walk-forward testing.
- Compare S1-S4 under identical costs.
- Minimum sample-size and drawdown gates before considering any live experiment.

## Explicitly excluded from V1
- Private keys
- Wallet signing
- Live Polymarket orders
- Copy-trading public wallets
- LLM in the low-latency execution path
