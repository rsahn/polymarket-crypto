# BONEREAPER - PRELIMINARY REVERSE ENGINEERING

## Dataset
- Snapshot: `analysis_bonereaper_snapshot.db` (3,590,758,400 bytes)
- Period: 2026-03-25T07:11:51+00:00 to 2026-05-03T17:24:00+00:00 (39.43 days)
- Fills: 2,296,021
- Markets: 26,638
- Snapshot is discovery/train data only; later imports remain validation/OOS.

## Top 10 quantitative discoveries
1. 2,296,021 fills across 26,638 markets. **Solid.**
2. Coverage spans 2026-03-25T07:11:51+00:00 to 2026-05-03T17:24:00+00:00. **Solid.**
3. BUY/SELL counts: {'BUY': 2293123, 'SELL': 2898}. **Solid.**
4. Outcome counts: {'Down': 1145309, 'Up': 1150712}. **Solid.**
5. P(next=DOWN | previous=UP) = 0.2137. **Solid descriptive, not predictive.**
6. P(next=UP | previous=DOWN) = 0.2145. **Solid descriptive, not predictive.**
7. Median fill size = 10.0; P99 = 255.0; max = 15152.0. **Solid.**
8. Mean fill notional = 20.1843 USDC; total observed notional = 46343560.81 USDC. **Solid observed flow, not capital.**
9. 25,464 markets have both outcome average-cost fields. **Descriptive only; not proof of economic pairing.**
10. Largest observed fill notional = 15000.48 USDC. **Solid observation.**

## Data quality
All missing-field and invalid-timestamp counters are zero in `data_quality.json`; duplicate key groups are zero in the snapshot.

## Inventory / temporal pairing
Signed inventory and accounting exposure are reconstructed per condition/outcome. Pair-cost fields are descriptive where both sides exist. No settlement-aware pairing, hedge rate, or arbitrage claim is made. A first leg alone is not treated as an arbitrage.

## Sizing / timing / price
The median size is 10.0, with mean 32.7337; rounded recurring blocks are recorded in `sizing_analysis.json`. Market open/expiry fields are absent from the activity rows, so time-from-open and late-window analysis are not testable in D0. Price buckets are in `sizing_analysis.json`.

## Capital minimum observable
Cumulative first-30-day observed trade notional: 38346435.92 USDC. This is **not** initial capital or wallet balance; deposits, withdrawals, inventory transfers, settlement and rebates are unavailable.

## Hypotheses
- H1 Temporal pairing: **IMPOSSIBLE TO CONFIRM** with settlement-unaware activity.
- H2 Inventory management: **DESCRIPTIVE ONLY**; inventory imbalance is measurable, intent is not.
- H3 Directional momentum: **IMPOSSIBLE TO TEST** without settlement/outcome evaluation.
- H4 Late window: **IMPOSSIBLE TO TEST** without reliable market open/expiry metadata.
- H5 Cross-market: **NOT TESTED in D0**.
- H6 SPRT/sequential evidence: **NOT TESTED in D0**.

## Limitations
Public activity can omit fills and does not provide complete settlement, wallet capital, rebates, or market lifecycle metadata. Snapshot is a discovery/train dataset. No live strategy, order, or Phase A/B/C code was changed.
