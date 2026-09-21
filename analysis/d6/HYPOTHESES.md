# D6 — H1 à H8 préparées, non testées

Associations prédictives, pas causalité démontrée. Huit familles primaires : un test principal préenregistré par famille, correction Holm des huit tests ; analyses secondaires exploratoires et registre complet. Un test non identifiable n'est ni positif ni négatif.

| ID | Hypothèse / mesure future | Entrées antérieures et target | Baseline / réfutation / limites |
|---|---|---|---|
| H1 INVENTORY REBALANCING | Probabilité du côté sous-pondéré augmente avec imbalance | Inventaire préalable ; Y_side | Random side conditionné, always rebalance ; contrôler prix/âge/liquidité ; aucune neutralité imposée |
| H2 PRICE OPPORTUNITY | Achat associé à prix exécutable inférieur au coût moyen existant | Gaps de coût UP/DOWN ; side et intensité | Always cheaper/prior empirique ; tester apport après imbalance ; coût initial inconnu exclu |
| H3 PAIR COST MANAGEMENT | Achat favorise une baisse attendue du coût combiné | Effet sur grille q connue, pas taille target ; Y_side | Pair ask threshold/alternance ; contre-exemples coût croissant ; première paire distincte |
| H4 BTC LEAD | Returns BTC antérieurs améliorent la prédiction du côté | Lags fixés ; Y_side | Modèle sans BTC, prior side ; ablation incrémentale ; timestamp de règlement ne prouve pas lead |
| H5 MICROSTRUCTURE | Spread/profondeur/imbalance expliquent le timing au-delà de l'âge | Grille achats ET non-achats ; hazard | Random timing conditionné/âge ; couverture identique positifs/négatifs ; pas de non-achats = non testable |
| H6 RESIDUAL DIRECTIONAL BET | Résidu conservé associé à l'information BTC antérieure | Résidu préalable, momentum ; prochain changement/côté | Modèle inventaire seul, permutation par blocs ; résidu futur est label ; stratégie privée inconnue |
| H7 MARKET AGE | Comportement varie avec la phase et améliore la prédiction | Avant fenêtre, premier tiers, milieu, fin ; durée | Modèle sans âge ; interactions groupées ; préfenêtre doit être réellement couverte |
| H8 SIZE POLICY | Quantité dépend d'opportunité, profondeur, imbalance, temps restant, vol | Features antérieures ; log(1+quantity_API), MAE/quantiles | Taille médiane/distribution TRAIN ; taille API != ordre ; cash réel du trader inconnu |

Modèles simples en première intention. Rapporter signes, incertitudes, calibration et amélioration hors échantillon, pas seulement p-values. Transformers et effets de durée/phase appris TRAIN. Dépendance par marché et blocs temporels ; marchés 5m/15m simultanés non indépendants. Une journée peut fournir trop peu de blocs pour une inférence robuste.

Contre-hypothèses : deux positions indépendantes, plusieurs stratégies, résidu délibéré, frais, activité manquante, règlement tardif. Examiner les achats qui augmentent l'imbalance et les paires finales >1. Les sensibilités sont préenregistrées et comptées ; ne pas sélectionner la variante la plus favorable. Une imitation réussie ne démontre ni mécanisme unique ni profit.
