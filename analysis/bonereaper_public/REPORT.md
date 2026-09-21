# Bonereaper — mécanique publique de trading et inventaire conditionnel

Rapport produit le 20 septembre 2026. Période principale : **13–19 septembre 2026 UTC**, marchés dont le début appartient à cette semaine. Extraction : 12 septembre 00:00:00–19 septembre 23:59:59 UTC, avec une journée antérieure pour les achats avant ouverture. Tous les horaires ci-dessous sont UTC, sans correction des timestamps sources.

**Conclusion principale. FACT : le profil actuel Bonereaper ne correspond pas à l’adresse proposée.** Le proxy vérifié est `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`. Les BTC 5m montrent une accumulation très fréquente des deux outcomes ; les BTC 15m ont un profil beaucoup plus unilatéral et majoritairement avant ouverture. Les coûts de paire sont variables et souvent supérieurs à 1. Une mécanique d’arbitrage garanti ou une causalité de rééquilibrage ne sont pas démontrées.

Cette étude est séparée de D5. Aucun accès à sa base active, aucune modification du collecteur ou de son superviseur, aucun ordre, aucune authentification de trading. Les scripts de cette étude lisent des API publiques et écrivent uniquement dans ce dossier. Les bases préexistantes, y compris `analysis_bonereaper_snapshot.db`, n’ont pas été utilisées ou modifiées.

## 1. Identité et sources utilisées

| Élément | Résultat |
|---|---|
| Profil demandé | [@bonereaper](https://polymarket.com/fr/@bonereaper) |
| Adresse fournie | `0xcd30457c790d8b35a08bcf3f894ad6bb52bc2dd0` |
| Proxy actuel du profil | `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30` |
| Nom retourné par Gamma pour ce proxy | Bonereaper |
| Adresse publique supplémentaire affichée dans la page (`walletAddress`) | `0x6732aa95a878efa81aa9eedbf51ce6d6cd7d8212` |
| Relation entre l’adresse fournie et Bonereaper | **UNKNOWN : non établie** ; ne pas conclure à un changement de wallet sans preuve |

Le HTML du profil contient `primaryAddress` et `proxyAddress` pour le proxy vérifié ; une requête indépendante au [profil public Gamma](https://gamma-api.polymarket.com/public-profile?address=0xeebde7a0e019a63e6b476eb425505b7b3e6eba30) retourne le même proxy et le nom Bonereaper. Les opérations de ce proxy indiquent également ce nom. Pour l’adresse fournie, Gamma retourne 404 et l’activité possède un nom vide. Cela ne prouve pas que les propriétaires sont distincts ; cela interdit simplement de fusionner les données. Les sondes de l’adresse fournie restent dans `raw/probe_*.body` et ne participent à aucun calcul.

| Source publique | Usage et preuves locales |
|---|---|
| [Profil web](https://polymarket.com/fr/@bonereaper) | `raw/profile.body`, `identity_verified.json` |
| [Gamma public-profile](https://gamma-api.polymarket.com/public-profile?address=0xeebde7a0e019a63e6b476eb425505b7b3e6eba30) | `raw/verified_gamma_profile.body` |
| [Data API activity](https://data-api.polymarket.com/activity?user=0xeebde7a0e019a63e6b476eb425505b7b3e6eba30&limit=10) | Source canonique du ledger, `raw/activity_*.body` |
| [Data API trades, takerOnly=false](https://data-api.polymarket.com/trades?user=0xeebde7a0e019a63e6b476eb425505b7b3e6eba30&takerOnly=false&limit=10) | Contrôle de 500 lignes datées du 19 septembre, `raw/crosscheck_trades.body` |
| [Gamma markets, closed=true](https://gamma-api.polymarket.com/markets?closed=true&limit=1) | Métadonnées de chacun des 2 049 marchés, `raw/metadata_batch_*.body` |
| [Exemple de marché Gamma](https://gamma-api.polymarket.com/markets/slug/btc-updown-5m-1789304400) | Horaires exacts, outcomes, tokens, règle de résolution |
| [Documentation activity](https://docs.polymarket.com/api-reference/core/get-user-activity) et [trades](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets) | Paramètres temporels, pagination, types d’opérations et filtre takerOnly |

Chaque réponse est conservée octet pour octet dans `.body`, avec URL complète, heure de récupération, statut HTTP, en-têtes et SHA-256 dans `.meta.json`. Les liens API sans fenêtre ci-dessus sont dynamiques : les preuves de cette étude sont les réponses locales horodatées. Le site web n’est pas utilisé comme source de prix par fill.

## 2. Qualité, observabilité et limites

- **FACT :** 92,638 lignes extraites, 92,637 opérations après déduplication par signature ; 261 fenêtres disjointes et contiguës. Chaque fenêtre terminale contient moins de 500 lignes. Les fenêtres pleines sont subdivisées, et ne sont pas ajoutées au dataset final. Aucun contournement de limite par offset ni ajout d’un fill manquant.
- Un doublon de signature concerne XRP, pas BTC. Sans identifiant de fill/log index, deux exécutions réellement identiques restent théoriquement possibles : la ligne écartée est conservée dans `duplicate_candidates.json`. Les statistiques BTC ne changent pas avec cette décision.
- **FACT :** 500/500 lignes de la source trades correspondent à activity sur hash, timestamp, condition, asset, side, quantité et prix. Les deux endpoints peuvent partager leur backend ; ce n’est pas une vérification indépendante de la blockchain.
- **FACT :** 2 049/2 049 marchés vérifiés dans Gamma : aucune divergence de slug, début, échéance, correspondance outcome/token ; aucun token ou hash manquant dans les trades BTC. Aucun trade antérieur à la création du marché dans ce contrôle.
- Empreintes brutes vérifiées sans écart ; couverture continue de l’intervalle demandé. Contrôle comptable indépendant sur 2 046 marchés sans événement de règlement précoce : aucune divergence. Six cas comptables synthétiques passent (achats, coût moyen après vente, cash, vente impossible, merge, état après redemption).

**FACT : les données sont des lignes publiques `TRADE`, appelées « fills API » dans les tableaux.** Elles ne prouvent ni le nombre d’ordres placés ni une granularité d’exécution élémentaire. Des prix fractionnaires peuvent être des moyennes d’exécutions regroupées ; aucune ligne n’est artificiellement divisée. Pas d’order ID, de log index, de carnet historique, de latence de décision ou de flux privé dans cette extraction.

Les timestamps sont à la seconde. L’ordre interne d’une seconde n’est pas déterminé : le ledger fournit un ordre d’affichage reproductible, jamais présenté comme l’ordre réel. Les statistiques de coût et d’inventaire utilisent les états en fin de seconde ; les alternances chronométrées excluent les transitions impliquant une seconde mixte UP+DOWN. Les maxima en fin de seconde peuvent sous-estimer un pic intraseconde.

**Anomalies conservées :** 135 lignes BTC 5m sur 45 marchés et 1 ligne BTC 15m sur un marché sont horodatées après l’échéance Gamma. Le retard maximal est 2 436 s en 5m, 986 s en 15m. Aucun timestamp n’a été décalé. Une publication ou un règlement tardif est une hypothèse, pas un fait établi. Ces lignes participent aux décomptes d’opérations récupérées et au ledger complet, mais pas aux états pré-échéance. Trois marchés n’ont aucun fill horodaté avant l’échéance ; leur état pré-échéance est UNKNOWN.

Les opérations avant le début de l’intervalle Up/Down sont possibles après la création du marché : début de la fenêtre de résolution et ouverture des échanges ne sont pas synonymes. La date `startDate` de Gamma n’est pas utilisée comme début des 5m/15m : `eventStartTime`/`events.startTime` confirme l’époque du slug.

**UNKNOWN : exhaustivité on-chain.** Les bornes de l’API sont couvertes mais les transferts ERC-1155, les éventuels wallets liés, opérations non indexées, frais exacts et brûlages de tokens n’ont pas été reconciliés avec des logs on-chain. L’inventaire ci-dessous est un inventaire **conditionnel aux opérations observées et à un inventaire initial nul**, pas une attestation du solde réel. La journée tampon limite la troncature initiale sans la prouver impossible. Les règlements après le 19 septembre sont censurés.

## 3. Statistiques séparées BTC 5m / BTC 15m

Dénominateurs : marchés distincts avec au moins une ligne TRADE dans la cohorte ; aucune extrapolation à toute la carrière du compte. Les coûts de paire finaux portent uniquement sur les marchés ayant une paire positive au dernier état pré-échéance connu.

| Mesure | BTC 5m | BTC 15m |
|---|---:|---:|
| Marchés | 1982 | 67 |
| Fills API | 62200 | 177 |
| BUY / SELL | 62200 / 0 | 177 / 0 |
| Fills/marché : moyenne / médiane / P95 | 31.38 / 28 / 70 | 2.64 / 2 / 7 |
| Marchés achetant UP et DOWN | 1936 (97.68 %) | 3 (4.48 %) |
| Paired qty finale : moyenne / médiane | 476.504 / 400.796 | 2.428 / 0.000 |
| Coût paire final brut : P05 / médiane / P95 | 0.743 / 1.003 / 1.287 | 1.009 / 1.031 / 1.032 |
| Coût paire final basé sur usdcSize : P05 / médiane / P95 | 0.763 / 1.023 / 1.305 | 1.044 / 1.066 / 1.067 |
| Marchés avec paire finale utilisée pour les coûts | 1933 | 3 |
| Délai legs opposés : moyenne / médiane (s) | 15.47 / 9 | 18.33 / 22 |
| Transitions opposées mesurables | 13214 | 3 |
| Quantité/fill : P05 / médiane / P95 | 1.660 / 20.000 / 160.000 | 10.792 / 42.000 / 136.224 |
| Quantité/fill : moyenne / maximum | 43.639 / 1 263.000 | 60.373 / 164.000 |
| Notionnel brut/fill : P05 / médiane / P95 | 0.525 / 8.209 / 82.370 | 4.988 / 20.640 / 68.574 |
| Déséquilibre final absolu en shares : médiane / P95 | 316.376 / 1 133.596 | 122.000 / 402.455 |
| Déséquilibre final normalisé absolu : médiane | 0.299 | 1.000 |
| Pic de déséquilibre en fin de seconde : médiane / maximum | 465.561 / 2 962.497 | 124.000 / 598.000 |
| Merges observés / redemptions observées | 6 / 1986 | 0 / 65 |

Les 6 merges observés interviennent après l’échéance. Des redemptions multiples pour une condition existent ; leur nombre n’est pas le nombre de marchés réglés. Un résidu directionnel reste souvent présent : paired qty ne signifie pas inventaire neutre.

### Distribution temporelle des opérations

| Position temporelle | BTC 5m | BTC 15m |
|---|---:|---:|
| Avant début de la fenêtre | 4630 (7.44 %) | 170 (96.05 %) |
| Premier tiers | 23297 (37.45 %) | 6 (3.39 %) |
| Tiers central | 22190 (35.68 %) | 0 (0.00 %) |
| Dernier tiers | 11948 (19.21 %) | 0 (0.00 %) |
| Horodatage après échéance | 135 (0.22 %) | 1 (0.56 %) |

### Coût moyen combiné : fréquence, magnitude, durée et quantité

| Seuil strict | 5m : % paires finales brut | 5m : % paires finales usdcSize | 5m : marchés ayant au moins un état sous le seuil | 5m : durée médiane positive dans les 300 s | 5m : médiane du maximum de quantité pairée pendant ces épisodes | 15m : % paires finales brut |
|---|---:|---:|---:|---:|---:|---:|
| < 1.0 | 48.99 % | 44.23 % | 1706 / 1982 | 170 s | 312.580 | 0.00 % |
| < 0.99 | 46.30 % | 41.08 % | 1643 / 1982 | 160 s | 308.518 | 0.00 % |
| < 0.98 | 43.82 % | 38.08 % | 1590 / 1982 | 151 s | 302.030 | 0.00 % |
| < 0.95 | 34.82 % | 30.57 % | 1417 / 1982 | 117 s | 283.523 | 0.00 % |

En 5m, le coût brut final des paires va de 0,318268 à 1,614773, moyenne 1,007158. La moyenne basée sur usdcSize est 1,025845. Parmi les épisodes sous 1 de durée positive, la durée moyenne est 166,06 s, la quantité pairée maximale médiane 312,58 shares et son maximum 2 741,55. Les durées sont des durées comptables conditionnelles entre observations, pas des fenêtres pendant lesquelles une paire était achetable au carnet. « Au moins un état » inclut l’avant-début ; la durée est limitée à la fenêtre du marché, d’où des dénominateurs différents.

Les pourcentages finaux 5m utilisent **1 933 marchés pairés**, les 15m **3 seulement**. En 15m, aucune des trois paires n’est sous 1 à un état mesuré ; cette taille d’échantillon ne permet pas une généralisation. Les distributions complètes P05/P25/médiane/P75/P95, minima, maxima et effectifs se trouvent dans `statistics.json`. La quantité retenue pour chaque épisode et les share-seconds sont dans `markets.json`.

**Sensibilité temporelle :** après exclusion de tous les marchés comportant un trade après échéance, il reste 1 891 marchés 5m pairés. La fréquence du coût final brut <1 est 49,02 %, contre 48,99 % dans le calcul principal ; basée sur usdcSize, 44,37 % contre 44,23 %. La conclusion principale résiste à cette exclusion. Cela ne répare pas les limites d’inventaire ou de frais.

## 4. Reconstruction de l’inventaire

À chaque BUY, ajouter la quantité et `price × size` au coût du côté concerné. À chaque SELL, retirer la quantité et son coût moyen pondéré courant ; une vente supérieure à la quantité observée rend l’inventaire UNKNOWN, sans inventer un achat antérieur. Un MERGE retire la même quantité des deux côtés, au coût moyen de chaque côté. Après REDEEM, le cash observé est conservé, mais les quantités résiduelles deviennent UNKNOWN car cette API ne permet pas ici de confirmer tous les brûlages. Aucun solde négatif n’est comblé artificiellement. Les erreurs d’arrondi flottant de l’ordre de 1e-14 ne représentent pas un short réel.

```text
up_qty, down_qty = quantités nettes observées avant règlement
up_cost_basis, down_cost_basis = coûts moyens pondérés résiduels (bruts)
average_up_cost = up_cost_basis / up_qty, si up_qty > 0
average_down_cost = down_cost_basis / down_qty, si down_qty > 0
paired_qty = min(up_qty, down_qty)
directional_up = max(up_qty - down_qty, 0)
directional_down = max(down_qty - up_qty, 0)
average_pair_cost = average_up_cost + average_down_cost, si paired_qty > 0
paired_cost_basis = paired_qty * average_pair_cost
inventory_imbalance = (up_qty - down_qty) / (up_qty + down_qty)
imbalance_shares = up_qty - down_qty
cash_flow_reported = cumul signé des usdcSize observés
```

Cette allocation pro rata aux shares pairées est une convention comptable ; elle ne prétend pas identifier des lots réellement appariés par le trader. Les moyennes de coût sont celles calculées à partir des lignes API, pas les valeurs de positions du profil. Aucun appariement favorable a posteriori ou inventaire caché n’est ajouté.

**Frais et cash :** `price × size` et `usdcSize` sont conservés séparément. Ils diffèrent sur 29 354 lignes BTC 5m et les 177 lignes BTC 15m, au-delà de 1e-5. Le supplément total observé est 24 254,93 en 5m et 186,38 en 15m. Il est compatible avec des frais, mais l’analyse ne certifie ni leur décomposition ni le cash net complet. Des rebates globaux sont présents dans l’extraction et non répartis arbitrairement entre marchés. `average_pair_cost_reported` utilise les dépenses `usdcSize` pour les achats, selon la même convention de coût moyen.

**Pas de PnL net certifié.** Un coût brut de paire <1 n’établit pas un profit global : il reste le résidu directionnel, les frais/rebates, les éventuels transferts et l’exhaustivité du règlement. Le cash-flow observé par marché est fourni, sans le renommer PnL. Les gagnants et prix de résolution sont stockés en métadonnées pour des contrôles futurs, pas pour inventer un redemption manquant.

## 5. Chronologies complètes de marchés instructifs

Sélection descriptive a posteriori, non représentative : extrême favorable avec 6–45 fills, contre-exemple coûteux, alternance élevée dans cette tranche, merge, puis un cas 15m pairé. Toutes les opérations API extraites pour ces marchés sont affichées, sans ellipse. Une même seconde garde un ordre d’affichage conventionnel. L’inventaire de chaque ligne est conditionnel ; seules les fins de seconde sont utilisées statistiquement. Les identifiants token/hash et la provenance de chaque ligne se trouvent dans le CSV.

### Marché 1 — btc-updown-5m-1789533600

[Marché public](https://polymarket.com/event/btc-updown-5m-1789533600) — condition `0x7fc425bb7f3dc1290ebc6042e72dffb0a7f52d79d43f896ae4aa815632d25a8f`. Motif de sélection : `pair_cost_below_095`. Début : 2026-09-16T04:40:00+00:00, durée 300 s.

```text
2026-09-16T04:40:28+00:00 BUY Up qty=10.000 prix_API=0.630000 usdcSize=6.463
  U=10.000 D=0.000 paire=0.000 residu_U=10.000 residu_D=0.000
  cout_U=6.300 cout_D=0.000 moy_U=0.630000 moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-6.463
2026-09-16T04:40:42+00:00 BUY Up qty=65.000 prix_API=0.810000 usdcSize=53.350
  U=75.000 D=0.000 paire=0.000 residu_U=75.000 residu_D=0.000
  cout_U=58.950 cout_D=0.000 moy_U=0.786000 moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-59.813
2026-09-16T04:40:52+00:00 BUY Down qty=53.000 prix_API=0.220000 usdcSize=12.297
  U=75.000 D=53.000 paire=53.000 residu_U=22.000 residu_D=0.000
  cout_U=58.950 cout_D=11.660 moy_U=0.786000 moy_D=0.220000 paire_brute=1.006000 paire_usdc=1.029524 cash_cumule=-72.110
2026-09-16T04:41:15+00:00 BUY Down qty=390.000 prix_API=0.181308 usdcSize=74.762
  U=75.000 D=443.000 paire=75.000 residu_U=0.000 residu_D=368.000
  cout_U=58.950 cout_D=82.370 moy_U=0.786000 moy_D=0.185937 paire_brute=0.971937 paire_usdc=0.994033 cash_cumule=-146.872
2026-09-16T04:41:33+00:00 BUY Down qty=24.330 prix_API=0.103288 usdcSize=2.671
  U=75.000 D=467.330 paire=75.000 residu_U=0.000 residu_D=392.330
  cout_U=58.950 cout_D=84.883 moy_U=0.786000 moy_D=0.181634 paire_brute=0.967634 paire_usdc=0.989517 cash_cumule=-149.543
2026-09-16T04:43:10+00:00 BUY Down qty=211.000 prix_API=0.023211 usdcSize=5.232
  U=75.000 D=678.330 paire=75.000 residu_U=0.000 residu_D=603.330
  cout_U=58.950 cout_D=89.781 moy_U=0.786000 moy_D=0.132355 paire_brute=0.918355 paire_usdc=0.937506 cash_cumule=-154.775
2026-09-16T04:44:00+00:00 BUY Up qty=5.000 prix_API=0.340000 usdcSize=1.779
  U=80.000 D=678.330 paire=80.000 residu_U=0.000 residu_D=598.330
  cout_U=60.650 cout_D=89.781 moy_U=0.758125 moy_D=0.132355 paire_brute=0.890480 paire_usdc=0.909893 cash_cumule=-156.554
2026-09-16T04:44:01+00:00 BUY Down qty=29.920 prix_API=0.651671 usdcSize=19.973
  U=80.000 D=708.250 paire=80.000 residu_U=0.000 residu_D=628.250
  cout_U=60.650 cout_D=109.279 moy_U=0.758125 moy_D=0.154294 paire_brute=0.912419 paire_usdc=0.932180 cash_cumule=-176.527
2026-09-16T04:44:13+00:00 BUY Up qty=348.000 prix_API=0.027388 usdcSize=10.180
  U=428.000 D=708.250 paire=428.000 residu_U=0.000 residu_D=280.250
  cout_U=70.181 cout_D=109.279 moy_U=0.163974 moy_D=0.154294 paire_brute=0.318268 paire_usdc=0.329972 cash_cumule=-186.707
2026-09-16T04:46:09+00:00 REDEEM qty=708.250 prix_API=0.000000 usdcSize=708.250
  U=UNKNOWN D=UNKNOWN paire=UNKNOWN residu_U=UNKNOWN residu_D=UNKNOWN
  cout_U=UNKNOWN cout_D=UNKNOWN moy_U=UNKNOWN moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=521.543
```

**FIN de fenêtre, dernier état connu :** UP 428.000, DOWN 708.250, paired qty 428.000, résidu signé UP−DOWN -280.250, coût moyen paire brut 0.318268, basé sur usdcSize 0.329972. Après les redemptions, le solde effectif final reste UNKNOWN ; il n’est pas forcé à zéro.

INFERENCE : accumulation successive de deux outcomes dont les prix ont changé ; le faible coût combiné peut résulter du parcours de prix. Ce cas extrême ne prouve pas une opportunité simultanée ou répétable.

### Marché 2 — btc-updown-5m-1789711800

[Marché public](https://polymarket.com/event/btc-updown-5m-1789711800) — condition `0x969c0ee79a299c13a4e832fce4009491a01e9f65b311853f6a36e87934bf291a`. Motif de sélection : `pair_cost_above_1`. Début : 2026-09-18T06:10:00+00:00, durée 300 s.

```text
2026-09-18T06:11:04+00:00 BUY Down qty=5.000 prix_API=0.610000 usdcSize=3.050 [ordre intraseconde UNKNOWN]
  U=0.000 D=5.000 paire=0.000 residu_U=0.000 residu_D=5.000
  cout_U=0.000 cout_D=3.050 moy_U=UNKNOWN moy_D=0.610000 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-3.050
2026-09-18T06:11:04+00:00 BUY Down qty=10.000 prix_API=0.610000 usdcSize=6.100 [ordre intraseconde UNKNOWN]
  U=0.000 D=15.000 paire=0.000 residu_U=0.000 residu_D=15.000
  cout_U=0.000 cout_D=9.150 moy_U=UNKNOWN moy_D=0.610000 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-9.150
2026-09-18T06:11:04+00:00 BUY Down qty=1.000 prix_API=0.610000 usdcSize=0.610 [ordre intraseconde UNKNOWN]
  U=0.000 D=16.000 paire=0.000 residu_U=0.000 residu_D=16.000
  cout_U=0.000 cout_D=9.760 moy_U=UNKNOWN moy_D=0.610000 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-9.760
2026-09-18T06:11:04+00:00 BUY Down qty=5.000 prix_API=0.610000 usdcSize=3.050 [ordre intraseconde UNKNOWN]
  U=0.000 D=21.000 paire=0.000 residu_U=0.000 residu_D=21.000
  cout_U=0.000 cout_D=12.810 moy_U=UNKNOWN moy_D=0.610000 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-12.810
2026-09-18T06:11:25+00:00 BUY Up qty=30.760 prix_API=0.460000 usdcSize=14.684
  U=30.760 D=21.000 paire=21.000 residu_U=9.760 residu_D=0.000
  cout_U=14.150 cout_D=12.810 moy_U=0.460000 moy_D=0.610000 paire_brute=1.070000 paire_usdc=1.087388 cash_cumule=-27.494
2026-09-18T06:11:28+00:00 BUY Down qty=1.860 prix_API=0.340000 usdcSize=0.632
  U=30.760 D=22.860 paire=22.860 residu_U=7.900 residu_D=0.000
  cout_U=14.150 cout_D=13.442 moy_U=0.460000 moy_D=0.588031 paire_brute=1.048031 paire_usdc=1.065419 cash_cumule=-28.127
2026-09-18T06:11:30+00:00 BUY Down qty=5.924 prix_API=0.340000 usdcSize=2.014
  U=30.760 D=28.784 paire=28.784 residu_U=1.976 residu_D=0.000
  cout_U=14.150 cout_D=15.457 moy_U=0.460000 moy_D=0.536983 paire_brute=0.996983 paire_usdc=1.014371 cash_cumule=-30.141
2026-09-18T06:11:33+00:00 BUY Up qty=58.000 prix_API=0.765741 usdcSize=45.141
  U=88.760 D=28.784 paire=28.784 residu_U=59.976 residu_D=0.000
  cout_U=58.563 cout_D=15.457 moy_U=0.659786 moy_D=0.536983 paire_brute=1.196769 paire_usdc=1.211000 cash_cumule=-75.282
2026-09-18T06:11:37+00:00 BUY Up qty=6.120 prix_API=0.710000 usdcSize=4.345
  U=94.880 D=28.784 paire=28.784 residu_U=66.096 residu_D=0.000
  cout_U=62.908 cout_D=15.457 moy_U=0.663025 moy_D=0.536983 paire_brute=1.200008 paire_usdc=1.213321 cash_cumule=-79.628
2026-09-18T06:11:39+00:00 BUY Up qty=6.000 prix_API=0.710000 usdcSize=4.346 [ordre intraseconde UNKNOWN]
  U=100.880 D=28.784 paire=28.784 residu_U=72.096 residu_D=0.000
  cout_U=67.168 cout_D=15.457 moy_U=0.665819 moy_D=0.536983 paire_brute=1.202802 paire_usdc=1.216180 cash_cumule=-83.974
2026-09-18T06:11:39+00:00 BUY Up qty=0.040 prix_API=0.710000 usdcSize=0.028 [ordre intraseconde UNKNOWN]
  U=100.920 D=28.784 paire=28.784 residu_U=72.136 residu_D=0.000
  cout_U=67.196 cout_D=15.457 moy_U=0.665836 moy_D=0.536983 paire_brute=1.202819 paire_usdc=1.216192 cash_cumule=-84.002
2026-09-18T06:11:45+00:00 BUY Down qty=47.000 prix_API=0.275319 usdcSize=13.596
  U=100.920 D=75.784 paire=75.784 residu_U=25.136 residu_D=0.000
  cout_U=67.196 cout_D=28.397 moy_U=0.665836 moy_D=0.374704 paire_brute=1.040540 paire_usdc=1.062575 cash_cumule=-97.599
2026-09-18T06:11:52+00:00 BUY Down qty=10.000 prix_API=0.320000 usdcSize=3.352
  U=100.920 D=85.784 paire=85.784 residu_U=15.136 residu_D=0.000
  cout_U=67.196 cout_D=31.597 moy_U=0.665836 moy_D=0.368327 paire_brute=1.034163 paire_usdc=1.056964 cash_cumule=-100.951
2026-09-18T06:12:16+00:00 BUY Down qty=1.735 prix_API=0.290000 usdcSize=0.503 [ordre intraseconde UNKNOWN]
  U=100.920 D=87.519 paire=87.519 residu_U=13.401 residu_D=0.000
  cout_U=67.196 cout_D=32.100 moy_U=0.665836 moy_D=0.366774 paire_brute=1.032610 paire_usdc=1.055224 cash_cumule=-101.454
2026-09-18T06:12:16+00:00 BUY Down qty=6.000 prix_API=0.290000 usdcSize=1.740 [ordre intraseconde UNKNOWN]
  U=100.920 D=93.519 paire=93.519 residu_U=7.401 residu_D=0.000
  cout_U=67.196 cout_D=33.840 moy_U=0.665836 moy_D=0.361848 paire_brute=1.027685 paire_usdc=1.049705 cash_cumule=-103.194
2026-09-18T06:12:16+00:00 BUY Down qty=10.000 prix_API=0.290000 usdcSize=2.900 [ordre intraseconde UNKNOWN]
  U=100.920 D=103.519 paire=100.920 residu_U=0.000 residu_D=2.599
  cout_U=67.196 cout_D=36.740 moy_U=0.665836 moy_D=0.354908 paire_brute=1.020744 paire_usdc=1.041929 cash_cumule=-106.094
2026-09-18T06:12:18+00:00 BUY Down qty=10.000 prix_API=0.290000 usdcSize=2.900
  U=100.920 D=113.519 paire=100.920 residu_U=0.000 residu_D=12.599
  cout_U=67.196 cout_D=39.640 moy_U=0.665836 moy_D=0.349190 paire_brute=1.015026 paire_usdc=1.035523 cash_cumule=-108.994
2026-09-18T06:12:21+00:00 BUY Up qty=60.000 prix_API=0.788333 usdcSize=48.001
  U=160.920 D=113.519 paire=113.519 residu_U=47.401 residu_D=0.000
  cout_U=114.496 cout_D=39.640 moy_U=0.711510 moy_D=0.349190 paire_brute=1.060700 paire_usdc=1.080566 cash_cumule=-156.995
2026-09-18T06:12:48+00:00 BUY Down qty=50.000 prix_API=0.253600 usdcSize=13.342
  U=160.920 D=163.519 paire=160.920 residu_U=0.000 residu_D=2.599
  cout_U=114.496 cout_D=52.320 moy_U=0.711510 moy_D=0.319961 paire_brute=1.031471 paire_usdc=1.053210 cash_cumule=-170.338
2026-09-18T06:13:06+00:00 BUY Up qty=67.690 prix_API=0.820000 usdcSize=55.506
  U=228.610 D=163.519 paire=163.519 residu_U=65.091 residu_D=0.000
  cout_U=170.002 cout_D=52.320 moy_U=0.743633 moy_D=0.319961 paire_brute=1.063594 paire_usdc=1.081561 cash_cumule=-225.844
2026-09-18T06:13:07+00:00 BUY Up qty=0.310 prix_API=0.820000 usdcSize=0.254
  U=228.920 D=163.519 paire=163.519 residu_U=65.401 residu_D=0.000
  cout_U=170.256 cout_D=52.320 moy_U=0.743737 moy_D=0.319961 paire_brute=1.063698 paire_usdc=1.081652 cash_cumule=-226.098
2026-09-18T06:13:13+00:00 BUY Down qty=5.000 prix_API=0.230000 usdcSize=1.212
  U=228.920 D=168.519 paire=168.519 residu_U=60.401 residu_D=0.000
  cout_U=170.256 cout_D=53.470 moy_U=0.743737 moy_D=0.317292 paire_brute=1.061029 paire_usdc=1.079084 cash_cumule=-227.310
2026-09-18T06:13:43+00:00 BUY Up qty=20.000 prix_API=0.642500 usdcSize=13.172
  U=248.920 D=168.519 paire=168.519 residu_U=80.401 residu_D=0.000
  cout_U=183.106 cout_D=53.470 moy_U=0.735603 moy_D=0.317292 paire_brute=1.052894 paire_usdc=1.071522 cash_cumule=-240.481
2026-09-18T06:13:52+00:00 BUY Down qty=14.000 prix_API=0.360000 usdcSize=5.266
  U=248.920 D=182.519 paire=182.519 residu_U=66.401 residu_D=0.000
  cout_U=183.106 cout_D=58.510 moy_U=0.735603 moy_D=0.320568 paire_brute=1.056170 paire_usdc=1.075337 cash_cumule=-245.747
2026-09-18T06:13:54+00:00 BUY Down qty=9.250 prix_API=0.430000 usdcSize=4.136
  U=248.920 D=191.769 paire=191.769 residu_U=57.151 residu_D=0.000
  cout_U=183.106 cout_D=62.487 moy_U=0.735603 moy_D=0.325846 paire_brute=1.061449 paire_usdc=1.080978 cash_cumule=-249.883
2026-09-18T06:14:07+00:00 BUY Down qty=78.000 prix_API=0.828387 usdcSize=65.390
  U=248.920 D=269.769 paire=248.920 residu_U=0.000 residu_D=20.849
  cout_U=183.106 cout_D=127.102 moy_U=0.735603 moy_D=0.471149 paire_brute=1.206751 paire_usdc=1.226266 cash_cumule=-315.274
2026-09-18T06:14:18+00:00 BUY Down qty=18.000 prix_API=0.990000 usdcSize=17.820 [ordre intraseconde UNKNOWN]
  U=248.920 D=287.769 paire=248.920 residu_U=0.000 residu_D=38.849
  cout_U=183.106 cout_D=144.922 moy_U=0.735603 moy_D=0.503603 paire_brute=1.239206 paire_usdc=1.258096 cash_cumule=-333.094
2026-09-18T06:14:18+00:00 BUY Down qty=26.570 prix_API=0.990000 usdcSize=26.304 [ordre intraseconde UNKNOWN]
  U=248.920 D=314.339 paire=248.920 residu_U=0.000 residu_D=65.419
  cout_U=183.106 cout_D=171.226 moy_U=0.735603 moy_D=0.544716 paire_brute=1.280319 paire_usdc=1.298418 cash_cumule=-359.398
2026-09-18T06:14:18+00:00 BUY Down qty=522.570 prix_API=0.990000 usdcSize=517.706 [ordre intraseconde UNKNOWN]
  U=248.920 D=836.909 paire=248.920 residu_U=0.000 residu_D=587.989
  cout_U=183.106 cout_D=688.570 moy_U=0.735603 moy_D=0.822753 paire_brute=1.558356 paire_usdc=1.571537 cash_cumule=-877.104
2026-09-18T06:16:42+00:00 REDEEM qty=836.909 prix_API=0.000000 usdcSize=836.909
  U=UNKNOWN D=UNKNOWN paire=UNKNOWN residu_U=UNKNOWN residu_D=UNKNOWN
  cout_U=UNKNOWN cout_D=UNKNOWN moy_U=UNKNOWN moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-40.195
```

**FIN de fenêtre, dernier état connu :** UP 248.920, DOWN 836.909, paired qty 248.920, résidu signé UP−DOWN -587.989, coût moyen paire brut 1.558356, basé sur usdcSize 1.571537. Après les redemptions, le solde effectif final reste UNKNOWN ; il n’est pas forcé à zéro.

FACT : le coût combiné termine nettement au-dessus de 1. Ce contre-exemple réfute une règle universelle qui imposerait toujours une paire finale rentable.

### Marché 3 — btc-updown-5m-1789580700

[Marché public](https://polymarket.com/event/btc-updown-5m-1789580700) — condition `0x36fc5d6055922df626b21f3746b32a8455b83f7bbc72972a518c9df2f8a8b3c1`. Motif de sélection : `frequent_alternation`. Début : 2026-09-16T17:45:00+00:00, durée 300 s.

```text
2026-09-16T17:44:33+00:00 BUY Down qty=122.000 prix_API=0.440000 usdcSize=55.784
  U=0.000 D=122.000 paire=0.000 residu_U=0.000 residu_D=122.000
  cout_U=0.000 cout_D=53.680 moy_U=UNKNOWN moy_D=0.440000 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-55.784
2026-09-16T17:44:55+00:00 BUY Down qty=65.000 prix_API=0.334412 usdcSize=22.750
  U=0.000 D=187.000 paire=0.000 residu_U=0.000 residu_D=187.000
  cout_U=0.000 cout_D=75.417 moy_U=UNKNOWN moy_D=0.403298 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-78.534
2026-09-16T17:44:57+00:00 BUY Down qty=93.000 prix_API=0.350000 usdcSize=34.031
  U=0.000 D=280.000 paire=0.000 residu_U=0.000 residu_D=280.000
  cout_U=0.000 cout_D=107.967 moy_U=UNKNOWN moy_D=0.385596 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-112.565
2026-09-16T17:44:58+00:00 BUY Down qty=176.000 prix_API=0.345880 usdcSize=63.662
  U=0.000 D=456.000 paire=0.000 residu_U=0.000 residu_D=456.000
  cout_U=0.000 cout_D=168.842 moy_U=UNKNOWN moy_D=0.370267 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-176.227
2026-09-16T17:45:09+00:00 BUY Up qty=63.000 prix_API=0.776825 usdcSize=49.705
  U=63.000 D=456.000 paire=63.000 residu_U=0.000 residu_D=393.000
  cout_U=48.940 cout_D=168.842 moy_U=0.776825 moy_D=0.370267 paire_brute=1.147092 paire_usdc=1.175424 cash_cumule=-225.932
2026-09-16T17:45:40+00:00 BUY Down qty=350.000 prix_API=0.204234 usdcSize=75.464
  U=63.000 D=806.000 paire=63.000 residu_U=0.000 residu_D=743.000
  cout_U=48.940 cout_D=240.323 moy_U=0.776825 moy_D=0.298168 paire_brute=1.074993 paire_usdc=1.101232 cash_cumule=-301.395
2026-09-16T17:45:43+00:00 BUY Up qty=232.000 prix_API=0.817198 usdcSize=192.016
  U=295.000 D=806.000 paire=295.000 residu_U=0.000 residu_D=511.000
  cout_U=238.530 cout_D=240.323 moy_U=0.808576 moy_D=0.298168 paire_brute=1.106744 paire_usdc=1.131663 cash_cumule=-493.411
2026-09-16T17:46:06+00:00 BUY Down qty=50.000 prix_API=0.270000 usdcSize=14.190
  U=295.000 D=856.000 paire=295.000 residu_U=0.000 residu_D=561.000
  cout_U=238.530 cout_D=253.823 moy_U=0.808576 moy_D=0.296523 paire_brute=1.105099 paire_usdc=1.130000 cash_cumule=-507.601
2026-09-16T17:46:15+00:00 BUY Down qty=52.000 prix_API=0.230000 usdcSize=12.605
  U=295.000 D=908.000 paire=295.000 residu_U=0.000 residu_D=613.000
  cout_U=238.530 cout_D=265.783 moy_U=0.808576 moy_D=0.292713 paire_brute=1.101289 paire_usdc=1.126093 cash_cumule=-520.206
2026-09-16T17:46:16+00:00 BUY Down qty=15.180 prix_API=0.270000 usdcSize=4.099
  U=295.000 D=923.180 paire=295.000 residu_U=0.000 residu_D=628.180
  cout_U=238.530 cout_D=269.882 moy_U=0.808576 moy_D=0.292340 paire_brute=1.100916 paire_usdc=1.125490 cash_cumule=-524.304
2026-09-16T17:46:18+00:00 BUY Down qty=10.000 prix_API=0.270000 usdcSize=2.838 [ordre intraseconde UNKNOWN]
  U=295.000 D=933.180 paire=295.000 residu_U=0.000 residu_D=638.180
  cout_U=238.530 cout_D=272.582 moy_U=0.808576 moy_D=0.292100 paire_brute=1.100676 paire_usdc=1.125251 cash_cumule=-527.142
2026-09-16T17:46:18+00:00 BUY Down qty=25.820 prix_API=0.270000 usdcSize=6.971 [ordre intraseconde UNKNOWN]
  U=295.000 D=959.000 paire=295.000 residu_U=0.000 residu_D=664.000
  cout_U=238.530 cout_D=279.553 moy_U=0.808576 moy_D=0.291505 paire_brute=1.100081 paire_usdc=1.124285 cash_cumule=-534.114
2026-09-16T17:46:21+00:00 BUY Up qty=51.000 prix_API=0.720000 usdcSize=37.440
  U=346.000 D=959.000 paire=346.000 residu_U=0.000 residu_D=613.000
  cout_U=275.250 cout_D=279.553 moy_U=0.795520 moy_D=0.291505 paire_brute=1.087025 paire_usdc=1.111715 cash_cumule=-571.553
2026-09-16T17:46:24+00:00 BUY Down qty=43.000 prix_API=0.350972 usdcSize=15.777
  U=346.000 D=1 002.000 paire=346.000 residu_U=0.000 residu_D=656.000
  cout_U=275.250 cout_D=294.645 moy_U=0.795520 moy_D=0.294057 paire_brute=1.089577 paire_usdc=1.114377 cash_cumule=-587.331
2026-09-16T17:46:33+00:00 BUY Up qty=48.000 prix_API=0.690000 usdcSize=33.839
  U=394.000 D=1 002.000 paire=394.000 residu_U=0.000 residu_D=608.000
  cout_U=308.370 cout_D=294.645 moy_U=0.782665 moy_D=0.294057 paire_brute=1.076722 paire_usdc=1.101969 cash_cumule=-621.169
2026-09-16T17:46:36+00:00 BUY Down qty=43.000 prix_API=0.327674 usdcSize=14.753
  U=394.000 D=1 045.000 paire=394.000 residu_U=0.000 residu_D=651.000
  cout_U=308.370 cout_D=308.735 moy_U=0.782665 moy_D=0.295440 paire_brute=1.078105 paire_usdc=1.103431 cash_cumule=-635.923
2026-09-16T17:46:46+00:00 BUY Down qty=250.000 prix_API=0.377200 usdcSize=98.411
  U=394.000 D=1 295.000 paire=394.000 residu_U=0.000 residu_D=901.000
  cout_U=308.370 cout_D=403.035 moy_U=0.782665 moy_D=0.311224 paire_brute=1.093889 paire_usdc=1.119769 cash_cumule=-734.334
2026-09-16T17:46:51+00:00 BUY Down qty=40.000 prix_API=0.470000 usdcSize=18.800
  U=394.000 D=1 335.000 paire=394.000 residu_U=0.000 residu_D=941.000
  cout_U=308.370 cout_D=421.835 moy_U=0.782665 moy_D=0.315981 paire_brute=1.098646 paire_usdc=1.124103 cash_cumule=-753.134
2026-09-16T17:46:57+00:00 BUY Up qty=40.000 prix_API=0.550000 usdcSize=22.693
  U=434.000 D=1 335.000 paire=434.000 residu_U=0.000 residu_D=901.000
  cout_U=330.370 cout_D=421.835 moy_U=0.761221 moy_D=0.315981 paire_brute=1.077203 paire_usdc=1.103173 cash_cumule=-775.827
2026-09-16T17:47:01+00:00 BUY Up qty=6.000 prix_API=0.600000 usdcSize=3.600 [ordre intraseconde UNKNOWN]
  U=440.000 D=1 335.000 paire=440.000 residu_U=0.000 residu_D=895.000
  cout_U=333.970 cout_D=421.835 moy_U=0.759023 moy_D=0.315981 paire_brute=1.075004 paire_usdc=1.100807 cash_cumule=-779.427
2026-09-16T17:47:01+00:00 BUY Up qty=7.775 prix_API=0.600000 usdcSize=4.665 [ordre intraseconde UNKNOWN]
  U=447.775 D=1 335.000 paire=447.775 residu_U=0.000 residu_D=887.225
  cout_U=338.635 cout_D=421.835 moy_U=0.756262 moy_D=0.315981 paire_brute=1.072243 paire_usdc=1.097836 cash_cumule=-784.092
2026-09-16T17:47:03+00:00 BUY Down qty=244.000 prix_API=0.420000 usdcSize=106.641
  U=447.775 D=1 579.000 paire=447.775 residu_U=0.000 residu_D=1 131.225
  cout_U=338.635 cout_D=524.315 moy_U=0.756262 moy_D=0.332055 paire_brute=1.088317 paire_usdc=1.114426 cash_cumule=-890.732
2026-09-16T17:47:04+00:00 BUY Down qty=40.000 prix_API=0.440000 usdcSize=18.290
  U=447.775 D=1 619.000 paire=447.775 residu_U=0.000 residu_D=1 171.225
  cout_U=338.635 cout_D=541.915 moy_U=0.756262 moy_D=0.334722 paire_brute=1.090984 paire_usdc=1.117168 cash_cumule=-909.022
2026-09-16T17:47:06+00:00 BUY Up qty=255.000 prix_API=0.600039 usdcSize=157.294
  U=702.775 D=1 619.000 paire=702.775 residu_U=0.000 residu_D=916.225
  cout_U=491.645 cout_D=541.915 moy_U=0.699577 moy_D=0.334722 paire_brute=1.034299 paire_usdc=1.062266 cash_cumule=-1 066.316
2026-09-16T17:47:16+00:00 BUY Down qty=84.800 prix_API=0.409410 usdcSize=36.153
  U=702.775 D=1 703.800 paire=702.775 residu_U=0.000 residu_D=1 001.025
  cout_U=491.645 cout_D=576.633 moy_U=0.699577 moy_D=0.338439 paire_brute=1.038016 paire_usdc=1.066114 cash_cumule=-1 102.469
2026-09-16T17:47:18+00:00 BUY Down qty=17.241 prix_API=0.420000 usdcSize=7.241
  U=702.775 D=1 721.041 paire=702.775 residu_U=0.000 residu_D=1 018.266
  cout_U=491.645 cout_D=583.875 moy_U=0.699577 moy_D=0.339257 paire_brute=1.038833 paire_usdc=1.066787 cash_cumule=-1 109.711
2026-09-16T17:47:36+00:00 BUY Up qty=1.610 prix_API=0.520000 usdcSize=0.837 [ordre intraseconde UNKNOWN]
  U=704.385 D=1 721.041 paire=704.385 residu_U=0.000 residu_D=1 016.656
  cout_U=492.482 cout_D=583.875 moy_U=0.699166 moy_D=0.339257 paire_brute=1.038423 paire_usdc=1.066345 cash_cumule=-1 110.548
2026-09-16T17:47:36+00:00 BUY Up qty=18.390 prix_API=0.520000 usdcSize=9.563 [ordre intraseconde UNKNOWN]
  U=722.775 D=1 721.041 paire=722.775 residu_U=0.000 residu_D=998.266
  cout_U=502.045 cout_D=583.875 moy_U=0.694608 moy_D=0.339257 paire_brute=1.033864 paire_usdc=1.061440 cash_cumule=-1 120.111
2026-09-16T17:47:40+00:00 BUY Down qty=42.000 prix_API=0.600000 usdcSize=25.906
  U=722.775 D=1 763.041 paire=722.775 residu_U=0.000 residu_D=1 040.266
  cout_U=502.045 cout_D=609.075 moy_U=0.694608 moy_D=0.345468 paire_brute=1.040076 paire_usdc=1.067711 cash_cumule=-1 146.016
2026-09-16T17:47:43+00:00 BUY Down qty=14.608 prix_API=0.490000 usdcSize=7.158 [ordre intraseconde UNKNOWN]
  U=722.775 D=1 777.649 paire=722.775 residu_U=0.000 residu_D=1 054.874
  cout_U=502.045 cout_D=616.232 moy_U=0.694608 moy_D=0.346656 paire_brute=1.041263 paire_usdc=1.068781 cash_cumule=-1 153.174
2026-09-16T17:47:43+00:00 BUY Down qty=0.390 prix_API=0.490000 usdcSize=0.191 [ordre intraseconde UNKNOWN]
  U=722.775 D=1 778.039 paire=722.775 residu_U=0.000 residu_D=1 055.264
  cout_U=502.045 cout_D=616.424 moy_U=0.694608 moy_D=0.346687 paire_brute=1.041295 paire_usdc=1.068809 cash_cumule=-1 153.365
2026-09-16T17:47:43+00:00 BUY Down qty=5.000 prix_API=0.490000 usdcSize=2.450 [ordre intraseconde UNKNOWN]
  U=722.775 D=1 783.039 paire=722.775 residu_U=0.000 residu_D=1 060.264
  cout_U=502.045 cout_D=618.874 moy_U=0.694608 moy_D=0.347089 paire_brute=1.041697 paire_usdc=1.069171 cash_cumule=-1 155.815
2026-09-16T17:47:49+00:00 BUY Down qty=22.000 prix_API=0.350000 usdcSize=7.700
  U=722.775 D=1 805.039 paire=722.775 residu_U=0.000 residu_D=1 082.264
  cout_U=502.045 cout_D=626.574 moy_U=0.694608 moy_D=0.347125 paire_brute=1.041732 paire_usdc=1.069034 cash_cumule=-1 163.515
2026-09-16T17:47:52+00:00 BUY Up qty=49.000 prix_API=0.703931 usdcSize=35.207
  U=771.775 D=1 805.039 paire=771.775 residu_U=0.000 residu_D=1 033.264
  cout_U=536.538 cout_D=626.574 moy_U=0.695200 moy_D=0.347125 paire_brute=1.042324 paire_usdc=1.069708 cash_cumule=-1 198.723
2026-09-16T17:48:21+00:00 BUY Down qty=43.000 prix_API=0.320000 usdcSize=14.415
  U=771.775 D=1 848.039 paire=771.775 residu_U=0.000 residu_D=1 076.264
  cout_U=536.538 cout_D=640.334 moy_U=0.695200 moy_D=0.346493 paire_brute=1.041693 paire_usdc=1.069105 cash_cumule=-1 213.138
2026-09-16T17:48:30+00:00 BUY Up qty=47.000 prix_API=0.686170 usdcSize=32.958
  U=818.775 D=1 848.039 paire=818.775 residu_U=0.000 residu_D=1 029.264
  cout_U=568.788 cout_D=640.334 moy_U=0.694681 moy_D=0.346493 paire_brute=1.041175 paire_usdc=1.068685 cash_cumule=-1 246.096
2026-09-16T17:48:37+00:00 BUY Down qty=185.000 prix_API=0.244595 usdcSize=47.643
  U=818.775 D=2 033.039 paire=818.775 residu_U=0.000 residu_D=1 214.264
  cout_U=568.788 cout_D=685.584 moy_U=0.694681 moy_D=0.337221 paire_brute=1.031902 paire_usdc=1.059312 cash_cumule=-1 293.739
2026-09-16T17:48:46+00:00 BUY Up qty=5.000 prix_API=0.790000 usdcSize=4.008
  U=823.775 D=2 033.039 paire=823.775 residu_U=0.000 residu_D=1 209.264
  cout_U=572.738 cout_D=685.584 moy_U=0.695260 moy_D=0.337221 paire_brute=1.032481 paire_usdc=1.059879 cash_cumule=-1 297.747
2026-09-16T17:49:00+00:00 BUY Down qty=43.000 prix_API=0.620000 usdcSize=27.369
  U=823.775 D=2 076.039 paire=823.775 residu_U=0.000 residu_D=1 252.264
  cout_U=572.738 cout_D=712.244 moy_U=0.695260 moy_D=0.343078 paire_brute=1.038338 paire_usdc=1.065789 cash_cumule=-1 325.116
2026-09-16T17:49:03+00:00 BUY Down qty=48.000 prix_API=0.681250 usdcSize=33.430
  U=823.775 D=2 124.039 paire=823.775 residu_U=0.000 residu_D=1 300.264
  cout_U=572.738 cout_D=744.944 moy_U=0.695260 moy_D=0.350720 paire_brute=1.045980 paire_usdc=1.073458 cash_cumule=-1 358.546
2026-09-16T17:49:06+00:00 BUY Down qty=10.000 prix_API=0.930000 usdcSize=9.300 [ordre intraseconde UNKNOWN]
  U=823.775 D=2 134.039 paire=823.775 residu_U=0.000 residu_D=1 310.264
  cout_U=572.738 cout_D=754.244 moy_U=0.695260 moy_D=0.353435 paire_brute=1.048694 paire_usdc=1.076107 cash_cumule=-1 367.846
2026-09-16T17:49:06+00:00 BUY Down qty=24.000 prix_API=0.930000 usdcSize=22.320 [ordre intraseconde UNKNOWN]
  U=823.775 D=2 158.039 paire=823.775 residu_U=0.000 residu_D=1 334.264
  cout_U=572.738 cout_D=776.564 moy_U=0.695260 moy_D=0.359847 paire_brute=1.055107 paire_usdc=1.082364 cash_cumule=-1 390.166
2026-09-16T17:49:16+00:00 BUY Up qty=177.000 prix_API=0.036045 usdcSize=6.811
  U=1 000.775 D=2 158.039 paire=1 000.775 residu_U=0.000 residu_D=1 157.264
  cout_U=579.118 cout_D=776.564 moy_U=0.578669 moy_D=0.359847 paire_brute=0.938516 paire_usdc=0.963823 cash_cumule=-1 396.976
2026-09-16T17:51:40+00:00 REDEEM qty=2 158.039 prix_API=0.000000 usdcSize=2 158.039
  U=UNKNOWN D=UNKNOWN paire=UNKNOWN residu_U=UNKNOWN residu_D=UNKNOWN
  cout_U=UNKNOWN cout_D=UNKNOWN moy_U=UNKNOWN moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=761.063
```

**FIN de fenêtre, dernier état connu :** UP 1 000.775, DOWN 2 158.039, paired qty 1 000.775, résidu signé UP−DOWN -1 157.264, coût moyen paire brut 0.938516, basé sur usdcSize 0.963823. Après les redemptions, le solde effectif final reste UNKNOWN ; il n’est pas forcé à zéro.

INFERENCE : achats des deux côtés et alternances fréquentes, compatibles avec gestion d’inventaire ou plusieurs signaux ; aucun carnet ni ordre annulé ne permet de conclure à du market making.

### Marché 4 — btc-updown-5m-1789845000

[Marché public](https://polymarket.com/event/btc-updown-5m-1789845000) — condition `0xbf545c18a3081a082ac520f21efca113cb42b24755dea36b92bc6b88f11c2fb7`. Motif de sélection : `merge`. Début : 2026-09-19T19:10:00+00:00, durée 300 s.

```text
2026-09-19T19:09:38+00:00 BUY Down qty=11.000 prix_API=0.510000 usdcSize=5.802
  U=0.000 D=11.000 paire=0.000 residu_U=0.000 residu_D=11.000
  cout_U=0.000 cout_D=5.610 moy_U=UNKNOWN moy_D=0.510000 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-5.802
2026-09-19T19:11:12+00:00 BUY Up qty=9.616 prix_API=0.270000 usdcSize=2.596
  U=9.616 D=11.000 paire=9.616 residu_U=0.000 residu_D=1.384
  cout_U=2.596 cout_D=5.610 moy_U=0.270000 moy_D=0.510000 paire_brute=0.780000 paire_usdc=0.797493 cash_cumule=-8.399
2026-09-19T19:11:14+00:00 BUY Up qty=1.370 prix_API=0.270000 usdcSize=0.370
  U=10.986 D=11.000 paire=10.986 residu_U=0.000 residu_D=0.014
  cout_U=2.966 cout_D=5.610 moy_U=0.270000 moy_D=0.510000 paire_brute=0.780000 paire_usdc=0.797493 cash_cumule=-8.769
2026-09-19T19:11:44+00:00 BUY Down qty=20.000 prix_API=0.430000 usdcSize=8.600
  U=10.986 D=31.000 paire=10.986 residu_U=0.000 residu_D=20.014
  cout_U=2.966 cout_D=14.210 moy_U=0.270000 moy_D=0.458387 paire_brute=0.728387 paire_usdc=0.734594 cash_cumule=-17.369
2026-09-19T19:12:32+00:00 BUY Down qty=21.000 prix_API=0.390000 usdcSize=8.190
  U=10.986 D=52.000 paire=10.986 residu_U=0.000 residu_D=41.014
  cout_U=2.966 cout_D=22.400 moy_U=0.270000 moy_D=0.430769 paire_brute=0.700769 paire_usdc=0.704470 cash_cumule=-25.559
2026-09-19T19:12:42+00:00 BUY Down qty=20.000 prix_API=0.480000 usdcSize=9.949
  U=10.986 D=72.000 paire=10.986 residu_U=0.000 residu_D=61.014
  cout_U=2.966 cout_D=32.000 moy_U=0.270000 moy_D=0.444444 paire_brute=0.714444 paire_usdc=0.721970 cash_cumule=-35.508
2026-09-19T19:13:08+00:00 BUY Down qty=62.000 prix_API=0.585161 usdcSize=37.334
  U=10.986 D=134.000 paire=10.986 residu_U=0.000 residu_D=123.014
  cout_U=2.966 cout_D=68.280 moy_U=0.270000 moy_D=0.509552 paire_brute=0.779552 paire_usdc=0.791458 cash_cumule=-72.842
2026-09-19T19:13:53+00:00 BUY Down qty=25.000 prix_API=0.730000 usdcSize=18.595
  U=10.986 D=159.000 paire=10.986 residu_U=0.000 residu_D=148.014
  cout_U=2.966 cout_D=86.530 moy_U=0.270000 moy_D=0.544214 paire_brute=0.814214 paire_usdc=0.826417 cash_cumule=-91.437
2026-09-19T19:14:05+00:00 BUY Down qty=1.200 prix_API=0.960000 usdcSize=1.152 [ordre intraseconde UNKNOWN]
  U=10.986 D=160.200 paire=10.986 residu_U=0.000 residu_D=149.214
  cout_U=2.966 cout_D=87.682 moy_U=0.270000 moy_D=0.547328 paire_brute=0.817328 paire_usdc=0.829440 cash_cumule=-92.589
2026-09-19T19:14:05+00:00 BUY Down qty=82.200 prix_API=0.959773 usdcSize=79.115 [ordre intraseconde UNKNOWN]
  U=10.986 D=242.400 paire=10.986 residu_U=0.000 residu_D=231.414
  cout_U=2.966 cout_D=166.575 moy_U=0.270000 moy_D=0.687192 paire_brute=0.957192 paire_usdc=0.966113 cash_cumule=-171.704
2026-09-19T19:14:05+00:00 BUY Down qty=46.600 prix_API=0.960000 usdcSize=44.736 [ordre intraseconde UNKNOWN]
  U=10.986 D=289.000 paire=10.986 residu_U=0.000 residu_D=278.014
  cout_U=2.966 cout_D=211.311 moy_U=0.270000 moy_D=0.731181 paire_brute=1.001181 paire_usdc=1.008664 cash_cumule=-216.440
2026-09-19T19:37:57+00:00 MERGE qty=10.986 prix_API=0.000000 usdcSize=10.986 [ordre intraseconde UNKNOWN]
  U=-0.000 D=278.014 paire=-0.000 residu_U=0.000 residu_D=278.014
  cout_U=-0.000 cout_D=203.278 moy_U=0.250000 moy_D=0.731181 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-205.454
2026-09-19T19:37:57+00:00 REDEEM qty=278.014 prix_API=0.000000 usdcSize=278.014 [ordre intraseconde UNKNOWN]
  U=UNKNOWN D=UNKNOWN paire=UNKNOWN residu_U=UNKNOWN residu_D=UNKNOWN
  cout_U=UNKNOWN cout_D=UNKNOWN moy_U=UNKNOWN moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=72.560
2026-09-19T19:38:36+00:00 REDEEM qty=0.000 prix_API=0.000000 usdcSize=0.000
  U=UNKNOWN D=UNKNOWN paire=UNKNOWN residu_U=UNKNOWN residu_D=UNKNOWN
  cout_U=UNKNOWN cout_D=UNKNOWN moy_U=UNKNOWN moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=72.560
```

**FIN de fenêtre, dernier état connu :** UP 10.986, DOWN 289.000, paired qty 10.986, résidu signé UP−DOWN -278.014, coût moyen paire brut 1.001181, basé sur usdcSize 1.008664. Après les redemptions, le solde effectif final reste UNKNOWN ; il n’est pas forcé à zéro.

FACT : le merge est réellement observable après échéance. Une baisse d’inventaire peut donc provenir d’un merge plutôt que d’une vente. Le cash reçu ne certifie pas le profit net.

### Marché 5 — btc-updown-15m-1789755300

[Marché public](https://polymarket.com/event/btc-updown-15m-1789755300) — condition `0x8441d8daa8e64ce28cccb6ed7c899642a14da96287b089d40aa1c4128f57ed5c`. Motif de sélection : `paired_15m_counterexample`. Début : 2026-09-18T18:15:00+00:00, durée 900 s.

```text
2026-09-18T18:14:36+00:00 BUY Down qty=97.000 prix_API=0.510000 usdcSize=51.167
  U=0.000 D=97.000 paire=0.000 residu_U=0.000 residu_D=97.000
  cout_U=0.000 cout_D=49.470 moy_U=UNKNOWN moy_D=0.510000 paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-51.167
2026-09-18T18:14:42+00:00 BUY Up qty=94.000 prix_API=0.520000 usdcSize=50.522
  U=94.000 D=97.000 paire=94.000 residu_U=0.000 residu_D=3.000
  cout_U=48.880 cout_D=49.470 moy_U=0.520000 moy_D=0.510000 paire_brute=1.030000 paire_usdc=1.064965 cash_cumule=-101.689
2026-09-18T18:14:43+00:00 BUY Up qty=13.000 prix_API=0.530000 usdcSize=7.117
  U=107.000 D=97.000 paire=97.000 residu_U=10.000 residu_D=0.000
  cout_U=55.770 cout_D=49.470 moy_U=0.521215 moy_D=0.510000 paire_brute=1.031215 paire_usdc=1.066176 cash_cumule=-108.806
2026-09-18T18:31:07+00:00 REDEEM qty=107.000 prix_API=0.000000 usdcSize=107.000
  U=UNKNOWN D=UNKNOWN paire=UNKNOWN residu_U=UNKNOWN residu_D=UNKNOWN
  cout_U=UNKNOWN cout_D=UNKNOWN moy_U=UNKNOWN moy_D=UNKNOWN paire_brute=UNKNOWN paire_usdc=UNKNOWN cash_cumule=-1.806
```

**FIN de fenêtre, dernier état connu :** UP 107.000, DOWN 97.000, paired qty 97.000, résidu signé UP−DOWN 10.000, coût moyen paire brut 1.031215, basé sur usdcSize 1.066176. Après les redemptions, le solde effectif final reste UNKNOWN ; il n’est pas forcé à zéro.

FACT : les deux côtés sont présents mais le coût de paire dépasse 1. Trois marchés seulement achètent les deux côtés en 15m ; ce comportement n’est pas représentatif du 5m.

## 6. Comportements récurrents et réponses A–J

| Question | Observation et degré de certitude |
|---|---|
| A — Achète les deux outcomes ? | FACT : 1 936/1 982 marchés 5m ; 3/67 en 15m. |
| B — Ordre des legs ? | FACT : premier groupe 5m Up sur 1 030 marchés, Down sur 932, mixte sur 18 ; 2 inconnus avant échéance. Transitions univoques : 6 628 Up→Down, 6 586 Down→Up. Ni priorité UP ni DOWN universelle. |
| C — Nombre de fills ? | FACT : médiane 28 en 5m, 2 en 15m ; ce ne sont pas des nombres d’ordres. |
| D — Intervalle opposé ? | FACT : médiane 9 s en 5m, 22 s en 15m, hors secondes mixtes. Heure de décision UNKNOWN. |
| E — Tailles ? | FACT : médiane 20 shares en 5m, 42 en 15m ; distributions ci-dessus. |
| F — Accumulation progressive ? | FACT : 1 977/1 982 marchés 5m ont plusieurs fills API ; aucun SELL observé. INFERENCE : accumulation progressive compatible avec ces séquences. |
| G — Rééquilibrage ? | FACT : sur 37 383 transitions de seconde avec déséquilibre préalable et nouvel achat 5m, 17 447 (46,67 %) achètent au moins un peu du côté sous-pondéré ; 15 175 (40,59 %) réduisent le déséquilibre absolu. INFERENCE : comportement non exclusivement rééquilibrant. Pas de causalité établie ni de comparaison à un modèle nul. |
| H — Imbalance maximal ? | FACT : maximum observé en fin de seconde 2 962,50 shares en 5m, 598 en 15m ; pics intraseconde inconnus. Le déséquilibre normalisé peut atteindre 1 dès le premier leg. |
| I — Moment ? | FACT : 5m répartis avant et pendant la fenêtre ; 170/177 lignes 15m sont avant son début. Pas une preuve de latence ni de signal futur. |
| J — Paire sous 1 ? | FACT : oui en 5m, parfois temporairement et parfois à la fin ; voir dénominateurs et sensibilité frais. Pas dans les 3 paires 15m observées. |

## 7. Hypothèses de stratégie — K

| Hypothèse | Éléments compatibles | Objections / test manquant | Statut |
|---|---|---|---|
| Accumulation de paires en 5m | Achats bilatéraux quasi systématiques, nombreuses alternances | Paires coûteuses et résidus directionnels fréquents ; objectifs internes inconnus | INFERENCE descriptive forte, HYPOTHESIS sur l’intention |
| Rééquilibrage d’inventaire | Certains achats du côté sous-pondéré diminuent le déséquilibre | La majorité des transitions éligibles ne le réduisent pas ; aucun modèle nul | HYPOTHESIS partielle |
| Spread capture / market making | Multiples prix, achats des deux outcomes, rebates dans l’activité globale | Pas de quotes, annulations, queue position ni maker/taker par ligne ; deux BUY ne prouvent pas un spread capturé | UNKNOWN |
| Mean reversion | Alternances et paires bon marché possibles après déplacement de prix | Pas de variation BTC ou carnet synchronisé dans cette étude | UNKNOWN |
| Momentum / pari directionnel | Inventaires déséquilibrés et 15m surtout unilatéraux | Aucun signal causal BTC ni connaissance des autres stratégies du même compte | HYPOTHESIS, UNKNOWN quant au signal |
| Multiples stratégies ou positions indépendantes | Contraste 5m/15m, résidus, niveaux de coût différents | Un seul proxy n’identifie ni bot ni sous-stratégie | HYPOTHESIS concurrente non réfutée |

## 8. Hypothèses rejetées et contre-épreuves

- **REJECTED pour cet échantillon :** « Bonereaper achète toujours les deux côtés » : 46 marchés 5m et 64 marchés 15m n’ont pas les deux outcomes achetés.
- **REJECTED :** « Chaque paire finale est verrouillée sous 1 » : 51,01 % des paires finales 5m ne sont pas sous 1 en brut ; les trois paires 15m dépassent 1.
- **REJECTED :** « Chaque nouvel achat réduit l’imbalance » : seulement 40,59 % des transitions éligibles 5m le réduisent.
- **REJECTED :** « Les prix de position affichés suffisent pour reconstruire les fills » : les calculs utilisent les lignes API, sans remplacer les exécutions manquantes par des moyennes du profil. Même une ligne API peut agréger des fills élémentaires.
- **NON ÉTABLI :** identité commune de l’adresse fournie et du proxy actuel.
- **NON RÉFUTÉ :** positions indépendantes, plusieurs stratégies, activités hors API, merges/redemptions/transferts manquants. L’absence de SELL dans l’extraction n’est pas une preuve d’absence de toute réduction de risque.
- **NON ÉTABLI :** cause de l’horodatage après échéance. La sensibilité qui exclut les marchés concernés ne rend pas les autres timestamps identiques à une heure de décision.

## 9. Informations manquantes et fichiers livrés

Pour certifier un inventaire réel et un PnL net, il faudrait réconcilier logs de transferts, splits/merges/redemptions et frais/rebates, connaître les soldes de départ, l’ordre intra-bloc et les éventuels comptes liés. Pour inférer le mécanisme d’exécution, il manquerait le carnet effectivement disponible, le rôle maker/taker de chaque exécution, les ordres non remplis/annulés et l’instant de décision. Aucun de ces éléments n’est inventé.

| Fichier | Contenu |
|---|---|
| `raw/` | Réponses source immuables par convention et métadonnées HTTP/SHA-256 |
| `activity_extracted.json`, `coverage.json` | Extraction et fenêtres terminales |
| `operations.csv` | Toutes opérations dédupliquées, champs demandés et provenance |
| `btc_inventory_ledger.csv` | État après chaque opération, coûts, paires, résidus, cash et incertitudes |
| `btc_second_states.csv` | États en fin de seconde utilisés par les statistiques |
| `opposite_transitions.csv` | Délais des transitions opposées non ambiguës |
| `markets.json`, `statistics.json` | Agrégats complets, quantités/durées/seuils |
| `market_metadata.json`, `metadata_validation.json` | Identité, échéances et tokens des 2 049 marchés |
| `validation.json`, `sensitivity_and_checks.json` | Contrôles, limites, sensibilité temporelle |
| `identity_verified.json`, `duplicate_candidates.json` | Identité et ambiguïté de déduplication |
| `D5_FUTURE_JOIN.md`, `future_join_schema.json` | Schéma de comparaison future, sans jointure exécutée |
| `fetch_public.py`, `extract.py`, `analyze.py`, `validate_markets.py`, `check_analysis.py`, `make_report.py` | Scripts autonomes ; aucune dépendance à D5 |

## 10. Pistes D5 à tester plus tard

**Aucune jointure exécutée.** Cette semaine historique s’arrête avant la collecte D5 actuelle : ces opérations ne peuvent pas être rapprochées de carnets D5 qui n’existaient pas à ces dates. Il faudra extraire séparément l’activité publique couvrant exactement la future fenêtre D5 validée. Le schéma est préparé dans `D5_FUTURE_JOIN.md`.

Après la fin et la validation qualité de D5, puis autorisation de la comparaison : joindre par `condition_id + token_id + durée + génération de marché`, utiliser des carnets disponibles avant la borne temporelle autorisée et conserver les bornes d’incertitude de T. Aucun nearest-neighbor tourné vers le futur. Respecter rotations, expirations, trous de données, timestamps source et réception. L’activité API ne livre pas l’heure de décision ; la comparaison répondra « quel état public enregistrait D5 autour de l’opération horodatée ? », pas « quel écran voyait réellement Bonereaper ? ».

Vérifier notamment l’imbalance préalable, la quantité achetée relativement au carnet, la variation BTC strictement antérieure, l’âge du marché, le coût de paire existant et le coût de l’autre leg. Comparer aussi des achats qui augmentent l’imbalance, des marchés où la paire reste >1 et les 15m avant ouverture. Les métadonnées Gamma de certains marchés citent une résolution Chainlink TWAP : ne pas assimiler automatiquement cette référence au flux BTC d’une autre source. Les tests futurs devront inclure des contrôles temporels, l’autocorrélation et la correction des tests multiples. Aucun backtest, optimisation, copie de profit ou D5 Research lancé ici ; `RESEARCH_ALLOWED` n’a pas été modifié.
