# BONEREAPER D2 — OPTIMAL REGIME DISCOVERY

READ-ONLY research analysis. D1 snapshot, matcher and pair database were not modified.

## Baseline
- PairCost weighted: **0.989884**
- GrossEdge weighted: **0.010116**
- Pairs: **1,826,848**

Note de cohérence: le JSON D1 publié indiquait `0.990744` comme PairCost pondéré. Le recalcul D2 par SQL aligné (`sum(pair_cost * paired_quantity) / sum(paired_quantity)`) donne **0.989884**. La différence vient de l'ancien agrégateur D1 qui chargeait `pair_cost` et `paired_quantity` par deux SELECT sans `ORDER BY`, puis les pondérait par position. La base `pair_observations.db` et les observations FIFO ne sont pas modifiées; D2 utilise le calcul SQL déterministe.

## Selection protocol
- Chronological 60% TRAIN / 20% VALIDATION / 20% OOS.
- No random split and no OOS tuning.
- Sub-second observations excluded from primary selection.
- Minimum: 10,000 pairs, 25 markets, 3 days, 2 weeks.
- `CHAMPION = NONE` is forced because unmatched first legs are absent and friction-adjusted net performance is not proven.

## Time regimes
| Window | Train pairs | Train weighted PairCost | Validation weighted PairCost | OOS weighted PairCost | OOS edge weighted |
|---|---:|---:|---:|---:|---:|
| 1-3s | 34,263 | 1.012392 | 1.007475 | 1.011165 | -0.011165 |
| 1-5s | 72,792 | 1.009337 | 1.005105 | 1.007868 | -0.007868 |
| 3-5s | 38,529 | 1.006597 | 1.002741 | 1.004809 | -0.004809 |
| 5-10s | 75,213 | 1.000380 | 0.999835 | 0.999029 | 0.000971 |
| 5-15s | 176,296 | 0.997135 | 0.997535 | 0.999465 | 0.000535 |
| 10-15s | 101,083 | 0.994700 | 0.995777 | 0.999798 | 0.000202 |
| 15-20s | 61,222 | 0.992085 | 0.996673 | 0.994413 | 0.005587 |
| 15-30s | 200,564 | 0.991621 | 0.993113 | 0.994212 | 0.005788 |
| 20-30s | 139,342 | 0.991415 | 0.991397 | 0.994124 | 0.005876 |
| 30-45s | 182,555 | 0.986020 | 0.990036 | 0.993829 | 0.006171 |
| 30-60s | 302,930 | 0.983346 | 0.986917 | 0.992181 | 0.007819 |
| 45-60s | 120,375 | 0.979197 | 0.982160 | 0.989777 | 0.010223 |
| 60-90s | 168,481 | 0.977072 | 0.982409 | 0.995331 | 0.004669 |
| 90-120s | 96,772 | 0.978895 | 0.988095 | 0.998718 | 0.001282 |
| >120s | 167,169 | 0.979619 | 1.035287 | 1.014556 | -0.014556 |

## Candidates
| Candidate | Train edge | Validation edge | OOS edge | OOS pairs | WF positive windows |
|---|---:|---:|---:|---:|---:|
| C1_FAST_PAIR | -0.009337 | -0.005105 | -0.007868 | 11,056 | 0 |
| C2_MEDIUM_PAIR | 0.002865 | 0.002465 | 0.000535 | 25,886 | 3 |
| C3_LATE_MEDIUM | 0.008379 | 0.006887 | 0.005788 | 29,684 | 4 |
| C4_INVENTORY_REBALANCE | 0.009933 | 0.017377 | 0.012895 | 4,004 | 1 |
| C5_SMALL_MEDIUM | 0.003850 | 0.002547 | 0.000202 | 25,144 | 3 |

## Inventory
- Low/medium/high/very-high inventory regimes are quantile-based; see `inventory_regimes.json`.
- Directional reduction is evaluated from persisted before/after fields.

## Direction
- UP→DOWN OOS weighted edge: 0.000204
- DOWN→UP OOS weighted edge: 0.001409

## Hedge completion
- Status: **NOT IDENTIFIABLE FROM PAIR_OBSERVATIONS**.
- The database stores completed pairs, not unmatched first legs; completion rates at 5/10/15/30/60 seconds cannot be estimated without an additional first-leg universe.

## Decision
- **CHAMPION V1: NONE**
- Reason: the apparent gross edge is not sufficient to establish a tradable regime without first-leg completion, execution friction, slippage and net settlement validation.

## Ten quantitative findings
1. D1 quantity is preserved as the reference; D2 uses the corrected FIFO database read-only.
2. Sub-second timing is excluded from selection because public timestamps are second-resolution.
3. Time windows are evaluated chronologically, not with random splits.
4. Candidate rules are limited to five simple interpretable rules.
5. OOS is evaluated after fixed candidate definitions, not used for tuning.
6. The 5–15 second window is explicitly tested rather than assumed optimal.
7. Size and time interactions are retained only above the minimum sample threshold.
8. Direction is evaluated conditionally but does not receive an invented bias.
9. Walk-forward results are reported per test week.
10. No candidate is promoted because hedge completion is not identifiable and all edges are gross simulations.

## Limitations
- FIFO is a reconstruction convention, not Bonereaper internal matching.
- Fills are not independent decisions and public activity may be incomplete.
- GrossPairEdge excludes fees, slippage, latency, failed second legs and rebates.
- No PnL or settlement is computed.
- No real trading or order execution occurred.
