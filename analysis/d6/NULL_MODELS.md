# D6 — modèles nuls préparés

Aucun modèle exécuté sur données réelles. Mêmes marchés, couverture, capital global 500, frais, latence et contraintes que la politique comparée. Seeds et répétitions préenregistrées, aucune meilleure seed retenue après coup.

| Modèle | Définition causale future | Usage |
|---|---|---|
| RANDOM_SIDE | p(UP)=0,5 ; variante prior durée/phase appris TRAIN | H1,H4,H6 |
| RANDOM_TIMING | Hazard âge/durée appris TRAIN, tirage en ligne sur opportunités valides | H5,H7 ; aucun nombre futur de fills |
| ALWAYS_REBALANCE | Côté sous-pondéré d'après inventaire préalable ; égalité départagée par seed | H1,H3 ; résidu non couvert conservé |
| ALWAYS_BUY_CHEAPER | Côté au coût exécutable unitaire minimal pour q fixé, frais compris | H2 ; profondeur insuffisante => no-action |
| FIXED_SIZE_ALTERNATING | q proposé=5 shares, cadence 10 s, changement de côté après fill confirmé | Alternance/accumulation ; jamais supposer second leg exécuté |
| PAIR_ASK_THRESHOLD | Pour q=5, tenter deux legs si sweep total avec frais <1 par paire | H3 ; exécution séquentielle, pas atomicité fictive |
| FIXED_SIZE / TRAIN_SIZE | Médiane ou distribution TRAIN de quantité par durée | H8 ; mêmes décisions side/timing pour isoler la taille |
| NO_TRADE | Aucune action, cash 500 | Sanité comptable et baseline économique |

Ces quantités/cadences sont références proposées, non optimisées aujourd'hui. Si minimum marché, tick ou budget empêche l'action, appliquer la règle de rejet gelée. Toute variante compte comme essai.

## Nul statistique ≠ politique exécutable

Une permutation conditionnelle peut conserver a posteriori nombre de fills/tailles dans un marché pour tester une association. Elle ne devient pas une stratégie et son PnL ne peut être qualifié d'exécutable. Garder features causales inchangées ; documenter blocs/labels échangés. RANDOM_TIMING exécutable n'utilise jamais nombre futur d'achats ou couverture future.

Comparaison side : log loss, Brier, calibration et balanced accuracy si nécessaire. Timing : hazard, précision/rappel avec taux de base. Taille : MAE et pertes quantiles. Comportement : distributions par marché et phase. Normalisation, priors, tailles et éventuelle imputation TRAIN seulement ; mêmes règles de censure et pondération.
