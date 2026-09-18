# Poly Quant Lab

Paper-trading research platform for short-duration Polymarket crypto markets.

## Goals
- Collect BTC market data and Polymarket order-book snapshots/events with timestamps.
- Reverse-engineer public behavioral patterns from benchmark traders: Bonereaper, BoneOhio, lkkdnfa.
- Compare four hypotheses under identical execution assumptions:
  - S1 Temporal Pairing
  - S2 Cross-market Z-score
  - S3 BTC -> Polymarket latency
  - S4 SPRT sequential evidence
- Measure net PnL, expectancy, drawdown, fill/hedge rate, pair cost, latency, and capacity.

## Safety / scope
V1 is PAPER ONLY. No private keys, wallet signing, or live order placement is implemented.

## Architecture
- Python 3.12 + asyncio backend
- SQLite event store for V1
- WebSocket collectors
- Deterministic strategy + risk engines
- Next.js/React dashboard planned after data pipeline is stable

## Run
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp ../config/.env.example ../config/.env
python -m app.main
```

## Data model
Every observation is timestamped with both source event time (when available) and local receive time. This is required for latency research.

## Benchmark traders
Configured in `config/benchmarks.json`. Public activity only; benchmark analysis is observational and does not copy orders in real time.
