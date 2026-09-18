# BONEREAPER D1 — Economic Reconstruction

Source: `analysis/bonereaper_snapshot.db` via `pair_observations.db`. Matching method: **FIFO convention**. No import, Gamma enrichment, bot, BoneOhio or lkkdnfa was run.

## Résumé

- Pairs: **1,826,848**
- Paired quantity: **21,732,275.514**
- PairCost mean: **0.99027792**
- PairCost median: **1.00000000**
- Quantity-weighted PairCost: **0.99074395**
- PairCost < 1: **48.822%** observations / **48.959%** quantity
- PairCost < 0.99: **44.948%** observations / **45.170%** quantity
- PairCost < 0.97: **38.278%** observations / **38.469%** quantity
- PairCost < 0.95: **32.719%** observations / **32.515%** quantity
- Median TimeToHedge: **40.000 s**
- Best PairCost bucket: **0-100ms** (0.412024)
- Worst PairCost bucket: **>120s** (1.254355)
- Paired inventory ratio: **28.971891%**
- Gross Pair Edge median: **0.00000000**
- Gross Pair Edge quantity weighted: **0.00925605**

## PairCost distribution

| Quantile | Value |
|---|---:|
| P01 | 0.501290 |
| P05 | 0.710000 |
| P10 | 0.800000 |
| P25 | 0.910000 |
| P50 | 1.000000 |
| P75 | 1.062467 |
| P90 | 1.170000 |
| P95 | 1.260000 |
| P99 | 1.480000 |

PairCost `< 1` est observé dans **48,822%** des lignes et **48,959%** de la quantité. PairCost `< 0,99`: **44,948% / 45,170%**. PairCost `< 0,97`: **38,278% / 38,469%**. PairCost `< 0,95`: **32,719% / 32,515%**. La pondération par quantité ne supprime donc pas le signal descriptif, mais elle ne constitue pas un profit net.

## TimeToHedge

| Mesure | Valeur |
|---|---:|
| Moyenne | 76,203 s |
| Médiane / P50 | 40,000 s |
| P10 | 6,000 s |
| P25 | 16,000 s |
| P75 | 82,000 s |
| P90 | 150,000 s |
| P95 | 226,000 s |
| P99 | 566,000 s |

| Bucket | Paires | Quantité | PairCost moyen | PairCost médian | `<1` | Gross edge moyen |
|---|---:|---:|---:|---:|---:|---:|
| 0–100 ms | 21,684 | 267,568 | 0.412024 | 0.440000 | 100.000% | 0.587976 |
| 100–500 ms | 0 | 0 | N/D | N/D | N/D | N/D |
| 500 ms–1 s | 0 | 0 | N/D | N/D | N/D | N/D |
| 1–5 s | 112,397 | 1,280,126 | 0.678254 | 0.690000 | 100.000% | 0.321746 |
| 5–15 s | 273,691 | 3,262,867 | 0.839998 | 0.846411 | 100.000% | 0.160002 |
| 15–30 s | 309,573 | 3,778,021 | 0.936871 | 0.940000 | 100.000% | 0.063129 |
| 30–60 s | 453,774 | 5,302,122 | 1.001129 | 1.000000 | 38.468% | -0.001129 |
| 60–120 s | 390,567 | 4,698,498 | 1.067923 | 1.060000 | 0.000% | -0.067923 |
| >120 s | 265,162 | 3,143,075 | 1.254355 | 1.210000 | 0.000% | -0.254355 |

Les timestamps publics sont en secondes: les sous-buckets 100–500 ms et 500 ms–1 s ne peuvent pas être distingués dans cette source; `0–100 ms` correspond aux fills dans la même seconde.

## Taille et marchés

- Les buckets `<10`, `10–50` et `50–100` représentent l'essentiel des observations, avec PairCost médian **1,00** et environ **48,8–49,0%** sous 1.
- Le bucket `250–500` a un GrossPairEdge moyen légèrement négatif (**-0,000278**); `500–1000` est également négatif (**-0,035368**), mais avec seulement 130 observations.
- Marchés avec paires: **25 464 / 26 638**.
- Distribution entre marchés de la médiane PairCost: P50 **0,994912**.
- Marchés dont la médiane PairCost est `<1`: **51,567%**; `<0,99`: **45,146%**; `<0,97`: **34,511%**; `<0,95`: **26,716%**.

## Inventaire et stabilité

- Paired inventory / achats traités: **28,9719%**.
- Seconde jambe réduisant l'imbalance: **96,310%** des observations.
- Réduction d'imbalance moyenne / médiane: **20,879 / 14,000 contrats**.
- Imbalance avant: moyenne **269,259**, médiane **133,023**; après: moyenne **248,379**, médiane **106,530**.
- Les rapports jour/semaine sont dans `d1_temporal_stability.json`; le signal n'est pas isolé à un seul jour, mais PairCost est sensible au délai: la zone 5–15 s est favorable descriptivement, tandis que 30–60 s est déjà autour de 1 et les délais plus longs au-dessus de 1.

## Dix découvertes quantitatives

1. La quantité appariée FIFO est **21,732 M**, presque identique à l'ancien total D1 (**-0,139%**).
2. La ligne FIFO corrigée est **1,827 M**, car les lots sont fragmentés; elle ne doit pas être comparée comme un compte d'événements 1:1 avec 955 177.
3. PairCost moyen corrigé: **0,990278**; médiane: **1,00**.
4. Le signal brut sous 1 couvre **48,822%** des observations et **48,959%** de la quantité.
5. La moyenne de GrossPairEdge est **0,009722**, mais sa médiane est **0**, donc la distribution est hétérogène.
6. La zone 5–15 s contient **273 691** paires, PairCost moyen **0,839998** et 100% sous 1 dans cette reconstruction.
7. Au-delà de 30 s, le signal se dégrade: PairCost moyen **1,001129** entre 30–60 s, **1,067923** entre 60–120 s et **1,254355** au-delà de 120 s.
8. UP→DOWN et DOWN→UP sont proches: PairCost moyen **0,990669** contre **0,989875**, et Hedge median 40 s dans les deux directions.
9. L'imbalance est réduite dans **96,310%** des secondes jambes, ce qui soutient une composante d'inventory management.
10. Le résultat est descriptif seulement: fees, slippage, latency, failed legs, settlement et rebates peuvent annuler le GrossPairEdge.

## Direction

| Direction | Pairs | Quantity | PairCost mean | PairCost median | Time median | PairCost < 1 | Gross edge mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| UP → DOWN | 926,314 | 11,063,033.116 | 0.990669 | 1.000000 | 40.000s | 48.926% | 0.009331 |
| DOWN → UP | 900,534 | 10,669,242.398 | 0.989875 | 1.000000 | 40.000s | 48.715% | 0.010125 |

## Conclusions disciplinées

- H1 Temporal Pairing: **PARTIALLY SUPPORTED** until direction, timing distributions and controls are interpreted; this dataset proves reconstructed two-leg sequences under FIFO, not Bonereaper's internal intent.
- H2 Inventory Management: **SUPPORTED** descriptively: 96,310% des secondes jambes réduisent l'imbalance, avec une réduction médiane de 14 contrats.
- Temporal stability: **see `d1_temporal_stability.json`**; period PairCost medians require the persisted rows and are not inferred from the old aggregate.

## Limites

- FIFO est une convention, pas l'appariement interne exact de Bonereaper.
- Les fills publics ne sont pas nécessairement complets et ne sont pas des décisions indépendantes.
- `GrossPairEdge = 1 - PairCost` n'est pas un profit net: frais, slippage, latence, risque d'exécution, jambe manquante et rebates sont exclus.
- La première jambe porte un risque directionnel.
- Le settlement/PnL reste hors périmètre de cette reconstruction.
