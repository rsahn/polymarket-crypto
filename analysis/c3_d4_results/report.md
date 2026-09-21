# D4 — NO EDGE

Décision figée : **NO_TRADE**, motif `NO_TRAIN_CANDIDATE`.
Aucune règle D4 retenue parmi les 98 filtres univariés prévus. Tous ont un PnL
TRAIN négatif, même avec la sortie proxy V4. Aucun candidat n'a été soumis à
la sélection VALIDATION et aucun résultat OOS n'a été consulté dans D4.
**Aucun moteur PAPER D4 préparé, aucun ordre réel envoyé, collector inchangé.**

Cette conclusion signifie « aucun edge robuste démontré dans le périmètre testé ».
Elle ne prouve pas l'impossibilité de toute autre stratégie.

## Données et séparation

- Source : `data/c3_shadow_live.db`, table `c3_shadow_observations_v2`.
- 269,562 lignes au total ; 262,080 lignes avec
  vrai slug ; 7,482 anciennes lignes exclues.
- 327 marchés réels : 245 BTC 5m et 82 BTC 15m.
- Manifeste 60/20/20 : 196 TRAIN, 65 VALIDATION, 66 OOS ; aucun slug partagé.
- Périmètre D3 5m : **147 TRAIN / 49 VALIDATION / 49 OOS**, avant filtre d'entrée.
- Ordre strictement identique au manifeste historique C3 V2.1. Les périodes 5m
  ne se chevauchent pas entre partitions. Les marchés 15m servent seulement au
  manifeste historique ; aucune observation 15m ne participe à D4.
- Snapshot SQLite cohérent : `snapshot.db`, empreinte `2caa840fd601ba87d370e1a5f57845605cf652a85c801c7f0e442e4148585552`.
- Les timestamps d'expiration viennent du vrai slug 5m (début UNIX + 300 s).
  Trois ancres TRAIN et une VALIDATION déjà expirées au timestamp de décision
  sont consignées et non tradables. La correction de précontrôle est auditée.

## D3 préservée et sélection D4

D3 : DOWN->UP, LEG1 DOWN, ask <= 0.14, première cotation admissible entre 15 et
30 secondes, friction 0.005 USDC par share appariée. Capital de départ 500 USDC,
budget nominal LEG1 10 USDC dans chaque partition/scénario indépendant.

D4 teste des filtres sur les features T0 proposées, à l'exception de nouvelles
optimisations du seuil `first_ask`. Durée, direction, délai, budget et friction
restent fixes. Trois variables dérivées T0 : couverture du carnet opposé,
coût estimé de la paire complète, capacité de sortie au bid. Quartiles TRAIN,
deux sens, aucune conjonction opportuniste. Les 98 règles et tous leurs résultats
TRAIN sont conservés dans `train_candidates.json`.

Les critères préenregistrés demandent notamment un PnL positif, un PnL positif
hors meilleur marché, au moins 80 % de hedges complets, au plus 5 % impossibles,
un DD <= 20 %, suffisamment de marchés et de trades, dans les deux scénarios.
**Le rejet ne dépend pas de ces seuils exigeants : aucun filtre n'est même rentable.**

| Sortie | Filtres TRAIN | PnL positifs | PnL minimum | PnL maximum |
| --- | --- | --- | --- | --- |
| v4_proxy | 98 | 0 | -407.88 | -107.43 |
| zero_recovery | 98 | 0 | -500.00 | -152.96 |

La validation affichée ci-dessous est celle du **D3 sans filtre**, fournie comme
diagnostic. Elle ne constitue pas une validation d'une règle D4 inexistante.
Il n'y a eu ni repêchage ni ajustement de seuil après consultation VALIDATION.

## Portefeuille conservateur chronologique — diagnostic D3 sans filtre

| Partition | Sortie LEG1 | Marchés disponibles | Marchés tradés | Signaux | Trades | Capital final | PnL USDC | DD USDC / % | Hedges C/R/I | Marchés +/− |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TRAIN | proxy V4 | 147 | 44 | 275 | 275 | 128.86 | -371.14 | 373.99 / 74.80 % | 64/59/152 | 0/44 |
| TRAIN | récupération nulle | 147 | 44 | 275 | 107 | 1.04 | -498.96 | 499.01 / 99.80 % | 44/55/8 | 0/44 |
| VALIDATION | proxy V4 | 49 | 15 | 120 | 120 | 355.97 | -144.03 | 146.90 / 29.38 % | 43/21/56 | 0/15 |
| VALIDATION | récupération nulle | 49 | 15 | 120 | 63 | 310.29 | -189.71 | 189.71 / 37.94 % | 41/20/2 | 0/15 |

C/R/I = hedge complet / réduit / impossible, classes exclusives par trade LEG1.
Le nombre de trades compte aussi les hedges impossibles. Tous les coûts LEG1
sont conservés ; les ledgers et les sommes par marché réconcilient le capital final.

| Partition | Sortie | Complet | Impossible | Réduit ou impossible | Edge net/share pairée | PnL paires | PnL LEG1 non couvert | Refus cash |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TRAIN | v4_proxy | 23.27 % | 55.27 % | 76.73 % | -0.017846 | -187.49 | -183.64 | 0 |
| TRAIN | zero_recovery | 41.12 % | 7.48 % | 58.88 % | -0.017047 | -128.13 | -370.84 | 168 |
| VALIDATION | v4_proxy | 35.83 % | 46.67 % | 64.17 % | -0.016949 | -96.73 | -47.30 | 0 |
| VALIDATION | zero_recovery | 65.08 % | 3.17 % | 34.92 % | -0.016896 | -92.85 | -96.86 | 57 |

L'edge net est pondéré par les shares effectivement appariées. Le PnL portefeuille
ajoute les ventes et pertes des portions non couvertes : il n'est pas calculé en
multipliant un edge conditionnel par une taille future connue à T0.

Le scénario récupération nulle peut afficher un taux de hedge complet supérieur
parce qu'il finance moins de nouvelles entrées pendant les mêmes marchés :
les trades refusés pour manque de cash ne sont pas des hedges complets ou impossibles.
Comparer ces taux sans leurs dénominateurs serait trompeur.

## Comparaison T0 des trois classes

Médianes, scénario proxy V4, D3 sans filtre :

| Partition | Label portefeuille | Trades | Ask LEG1 médian | Couverture carnet T0 médiane | Cash paire T0 médian USDC | Temps restant médian s |
| --- | --- | --- | --- | --- | --- | --- |
| TRAIN | complete | 64 | 0.100 | 2.31 | 92.27 | 94.5 |
| TRAIN | reduced | 59 | 0.070 | 1.48 | 126.88 | 67.7 |
| TRAIN | impossible | 152 | 0.060 | 1.77 | 145.00 | 44.1 |
| VALIDATION | complete | 43 | 0.090 | 3.48 | 86.65 | 120.1 |
| VALIDATION | reduced | 21 | 0.080 | 1.91 | 126.88 | 101.7 |
| VALIDATION | impossible | 56 | 0.060 | 1.74 | 126.88 | 52.5 |

La demande est `min(10/first_ask, first_ask_qty)`. Le financement estimé est cette
demande multipliée par `first_ask + opposite_ask + 0.005`. Un LEG1 de 10 USDC
peut donc exiger environ 90–145 USDC pour compléter la paire aux médianes observées.
Les classes incomplètes présentent des besoins de financement supérieurs ;
la seule profondeur opposée T0 ne garantit pas le cash LEG2 au moment du hedge.

TRAIN : capacité future du carnet seul = {'complete': 178, 'reduced': 60, 'impossible': 37}.
VALIDATION : capacité future du carnet seul = {'complete': 80, 'reduced': 27, 'impossible': 13}.
Ces labels ignorent volontairement les contraintes de cash ; les statuts du
portefeuille les intègrent. Les absences de future cotation admissible dans les
lignes conservées sont classées impossibles, pas éliminées après coup.

Les CSV `*_feature_comparison.csv` donnent effectifs, marchés, valeurs manquantes
et quartiles pour les 15 features brutes et les trois dérivées, selon les deux
types de labels. `diagnostic_audit.json` documente aussi les zéros et cardinalités.
Les retours BTC ont une médiane nulle dans ces groupes ; aucune causalité des
retours BTC sur le hedge n'est démontrée par cette comparaison.

## Pourquoi l'ancien V4 et cette simulation divergent

Référence : fonction V4 originale importée sans modification, exécutée seulement
sur les partitions de développement et les mêmes signaux admissibles à T0 :

| Partition | V4 original capital final | V4 original PnL | Paires comptées V4 |
| --- | --- | --- | --- |
| TRAIN | 544.38 | +44.38 | 213 |
| VALIDATION | 438.33 | -61.67 | 67 |

V4 traite les deux jambes à T0, utilise une cotation future sans vérifier qu'elle
précède l'expiration, et ne répartit pas toutes les pertes non couvertes dans son
ledger de paires. Son champ `completed_pairs` inclut aussi des hedges réduits ;
ses résultats par marché ne doivent pas être pris pour une comptabilité complète.

Sur les signaux D3 dédupliqués :

- TRAIN : 37 cotations LEG2 après expiration,
  37 edges apparents positifs parmi les cotations invalides.
- VALIDATION : 13 cotations LEG2 après expiration,
  13 edges apparents positifs parmi les cotations invalides.
- Parmi les cotations temporellement valides : seulement
  5 signaux à edge positif TRAIN et
  1 VALIDATION, avant contraintes de portefeuille.

L'observateur conserve ses queues sous la clé « 5m », puis applique la cotation du
snapshot courant à une ancienne ancre sans comparer les slugs. Cela permet des
appariements entre marchés successifs. Les 50 cotations post-expiration ne sont
pas des hedges exécutables du marché LEG1. Leur token LEG2 n'étant pas persisté,
on ne prétend pas identifier précisément chaque marché de provenance.

D4 traite LEG1 à T0, LEG2 à son heure observée, et invalide ces hedges. Il conserve
la perte LEG1. À heure identique : règlement, hedge, entrée. Les sorties n'apportent
du cash qu'au moment de l'échec simulé ; les paires ne libèrent du cash qu'à expiration.
Le défaut du collector est **documenté, pas modifié**, conformément à la demande.

## Stabilité et concentration

Avec sortie proxy, les 44 marchés tradés TRAIN et les 15 VALIDATION sont tous
déficitaires. Il n'existe donc aucun gain positif dont calculer la concentration.
La part des cinq plus grandes pertes dans la somme des PnL absolus est
23.37% TRAIN et
51.15% VALIDATION.

| Partition | Extrême | Marché | PnL USDC |
| --- | --- | --- | --- |
| TRAIN | best_market | btc-updown-5m-1789800900 | -0.0333 |
| TRAIN | worst_market | btc-updown-5m-1789768200 | -19.3515 |
| VALIDATION | best_market | btc-updown-5m-1789818300 | -0.3571 |
| VALIDATION | worst_market | btc-updown-5m-1789812600 | -18.3747 |

Les fichiers `*_markets.csv` fournissent le PnL et les trois classes de hedge
pour chaque marché. Les métriques incluent le PnL hors meilleur marché et la part
du meilleur marché dans les gains positifs (null lorsqu'il n'existe aucun gain).
Les intervalles bootstrap par marché de `development.json` sont descriptifs :
les marchés successifs peuvent être dépendants et la période est courte.

## Résultat OOS et décision finale

**OOS non ouvert pour D4.** Aucun filtre ne passe TRAIN ; il n'existe donc aucune
règle de trading sélectionnée sur TRAIN + VALIDATION à tester honnêtement en OOS.
Les résultats OOS de trading sont **non évalués**, pas zéro ni un succès simulé.

La politique retenue est l'abstention : **500 -> 500 USDC**, PnL 0, drawdown 0,
0 trade, 0 hedge complet/réduit/impossible, 0 marché gagnant/perdant.
Ce résultat est une identité comptable de l'absence de positions ; il ne constitue
ni un backtest OOS ni une preuve d'edge. `frozen_rule.json` et `final.json` fixent
cette décision. L'OOS historique avait déjà été utilisé par C3 V2.1/V4 : même une
première lecture dans D4 n'aurait pas recréé un échantillon prospectif vierge.

## Hypothèses et limites restantes

1. L'observateur ne persiste pas les ancres sans carnet futur valide. Les taux
   calculés sont conditionnels à cet enregistrement ; le vrai taux d'échec live
   ne peut pas être estimé sans le dénominateur complet des ancres T0.
2. Le bid et sa profondeur après échec ne sont pas enregistrés dans cette table.
   La sortie au bid T0 est le proxy de V4, pas une transaction attestée ; elle
   peut être optimiste, notamment lorsque le hedge expire avec le marché.
   Le scénario récupération nulle expose cette incertitude sans remboursement.
3. Les bases brutes portent `market_id=5m/15m`. `poly_quotes` possède des tokens,
   mais pas de table de liaison vérifiée token/condition/slug. Les anciennes
   observations anonymes ne sont pas réattribuées à des marchés par simple arrondi.
4. Profondeur limitée au meilleur prix. Une cotation de hedge partagée au même
   timestamp ne peut pas être consommée deux fois. Entre snapshots distincts,
   la profondeur affichée est supposée disponible à nouveau : pas de modèle
   contrefactuel de notre impact, de file d'attente, latence ou replenishment.
5. Friction fixée à 0.005 par share pairée, conformément à D3 ; elle n'est pas
   une vérification des frais actuels. Pas de frais additionnels inventés sur
   les résidus. Budget nominal : remplissages partiels et très petites tailles
   possibles, sans minimum d'ordre réel modélisé.
6. Paires réglées au timestamp d'expiration du slug, délai réel de résolution
   non modélisé. Aucun gain directionnel final n'est inventé pour les résidus.
7. DD = cash + valeur certaine des paires, jambes en attente à zéro. C'est une
   valorisation sévère et explicite, pas un mark-to-market de liquidation.
8. Il s'agit d'associations T0/futur avec décisions sans look-ahead, **pas d'une
   identification d'effet causal**. Le statut portefeuille dépend aussi des
   entrées précédentes et du cash disponible. Les filtres ont été testés sur une
   courte période déjà explorée historiquement.

Ces limites interdisent de préparer un moteur PAPER D4 au titre d'une validation
réaliste positive. Aucune nouvelle instrumentation live n'est appliquée ici.

## Reproduction et vérifications

```powershell
python -m unittest discover -s analysis -p test_c3_d4_analysis.py -v
python analysis/c3_d4_report.py
```

Pour une nouvelle recherche sur un échantillon explicitement autorisé, les étapes
sont `prepare`, `develop`, `finalize` avec le même `--out`. Le dossier de cette
recherche est déjà finalisé : ne pas effacer ses marqueurs ni recycler cet OOS.
Le script refuse l'écrasement du snapshot, une nouvelle sélection après gel et
une seconde finalisation. Il vérifie les empreintes de code, protocole et données.

12 tests synthétiques ont validé la séparation T0/labels, le cooldown, les pertes
LEG1, la profondeur partagée, les événements entrelacés, le règlement à expiration,
le DD, les partitions et le verrou OOS. Aucune connexion réseau ni ordre réel.
