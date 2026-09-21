# D6 — schéma des features candidates

Aucun calcul sur D5. Toutes les entrées respectent JOIN_SPEC à la borne B. Champs obligatoires : nom/version, unité, fenêtre, clés fortes, event IDs, temps source/receive/available, âge, coverage, status VALID/UNKNOWN/EXCLUDED et raison. UNKNOWN n'est pas 0. Imputation/normalisation apprises TRAIN uniquement. Le target courant (côté, taille, prix réellement exécuté) n'est pas une feature.

## Polymarket

Notation par outcome : b/a = best bid/ask, qb/qa = quantités ; mid=(a+b)/2. Vérifier niveaux triés, quantités positives, prix dans [0,1], carnet non croisé. Un côté absent n'est pas inventé.

| Feature | Formule / unité |
|---|---|
| up/down_best_bid, best_ask | Prix de probabilité du premier niveau |
| up/down_bid_qty, ask_qty | Shares du premier niveau |
| up/down_spread, midpoint | a-b ; (a+b)/2 |
| up/down_top_imbalance | (qb-qa)/(qb+qa), NULL si dénominateur nul |
| up/down_depth_bid_qty_5, depth_ask_qty_5 | Sommes des 5 premiers niveaux ; préciser nombre réellement disponible |
| up/down_depth_imbalance_5 | (somme bids-somme asks)/(somme bids+somme asks) |
| up/down_microprice | (a*qb+b*qa)/(qb+qa), proxy non exécutable |
| spread_asymmetry | spread_UP-spread_DOWN |
| liquidity_ratio_up_down | depth_ask_UP/depth_ask_DOWN, NULL si zéro |
| pair_ask_top | ask_UP+ask_DOWN, prix infinitésimal seulement |
| pair_ask_executable_q | [sweep_UP(q)+sweep_DOWN(q)]/q pour grille fixée q=1,5,10 shares ; NULL si profondeur insuffisante |
| pair_cash_required_q | Deux sweeps + frais vérifiés, gross_only si frais inconnus |
| market_age_ms | B-début de fenêtre ; négatif autorisé avant fenêtre |
| time_remaining_ms | échéance-B, >0 |
| phase | pre_window / first_third / middle_third / last_third |
| up/down_midpoint_change_h | mid(B)-mid(B-h), points de probabilité |
| up/down_spread_change_h | spread(B)-spread(B-h) |

Horizons h : **250 ms, 500 ms, 1 s, 3 s, 5 s, 10 s, 15 s, 30 s**. Chaque lag a sa propre sélection as-of/fraîcheur, même identité et génération. Aucune interpolation avec une donnée future. Les deux outcomes d'une paire doivent être simultanément admissibles.

Les quantités q sont fixées avant observation des résultats, jamais égales au fill futur. La précision 250 ms des ticks n'annule pas l'incertitude seconde/retard de l'API Bonereaper : ces colonnes peuvent rester non identifiables.

## BTC

| Feature | Formule et couverture |
|---|---|
| btc_return_h | P(B)/P(B-h)-1, huit horizons ci-dessus, prix positifs |
| btc_log_return_h | log(P(B)/P(B-h)), représentation alternative préenregistrée |
| btc_local_vol_30s | Écart-type échantillonnal de 30 returns sur grille 1 s ; 31 points admissibles exigés, sinon NULL |
| btc_acceleration_1s | return de la dernière seconde moins celui de la seconde précédente |
| btc_momentum_contrast | return_3s-return_15s/5, proxy descriptif |
| poly_btc_dislocation_h | delta mid_UP_h-beta_h*btc_return_h ; beta TRAIN figé, unités documentées |

Toutes les fenêtres sont passées, avec règles strictes aux bornes. Pas de remplissage à travers gaps/reconnexions. Une version normalisée utilise échelles TRAIN ; ne pas soustraire sans conversion des dollars BTC et une probabilité. Conserver le feed et la référence oracle : Chainlink TWAP et spot Binance ne sont pas équivalents.

## Inventaire Bonereaper préalable

| Feature | Convention |
|---|---|
| up_qty/down_qty | Quantités nettes de la condition avant la seconde cible |
| average_up/down_cost | Coût moyen pondéré résiduel ; versions price*size et usdcSize distinctes |
| paired_qty | min(up_qty,down_qty) |
| pair_cost | Somme des coûts moyens si les deux côtés existent ; sinon NULL |
| directional_up/down | max(up-down,0), max(down-up,0) |
| inventory_imbalance | (up-down)/(up+down) ; NULL si inventaire nul, flag zero_inventory séparé |
| imbalance_shares | up-down |
| last_buy_side | UP / DOWN / BOTH_SAME_SECOND / UNKNOWN |
| since_buy_up/down_ms | Temps depuis dernière seconde antérieure pour chaque côté, incertitude conservée |
| since_opposite_buy_if_up/if_down_ms | Deux colonnes candidates, sans choisir avec le côté target |
| previous_buy_qty, last_3_buy_qty_sum/mean | Fills API antérieurs, pas tailles d'ordres supposées ; groupes ambigus conservés |
| pair_cost_change_if_buy_side_q | Effet comptable hypothétique sur grille q au coût exécutable connu, frais séparés |
| relative_cost_opportunity_side | Coût exécutable unitaire moins coût moyen antérieur du même côté |

Transferts/splits/merges/redemptions intégrés s'ils sont reconstructibles, sinon UNKNOWN. Aucune position finale ou moyenne du profil pour remplir le passé. Aucun lot choisi a posteriori. Les inventaires d'une politique indépendante proviennent de SON ledger, pas du futur inventaire de Bonereaper.

## Targets isolés

Y_side, Y_timing, Y_size et résultats futurs dans une table séparée avec leur intervalle/availability. Variables interdites dans X : winner, resolution, future_return, next_fill, future_cash, target_side, target_size, pnl. Aucun futur utilisé pour décider d'inclure une feature ; les exclusions qualité rétrospectives restent des métadonnées d'audit.
