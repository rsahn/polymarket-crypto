# D4 — protocole fixé avant lecture des résultats TRAIN / VALIDATION

Date : 2026-09-20. Recherche locale SHADOW, aucun ordre, collector inchangé.

## Architecture inspectée

`backend/app/main.py` orchestre Binance, découverte Polymarket, carnets WebSocket,
rotation 5m/15m, SQLite et audit PAPER. `collectors/` acquiert les données publiques ;
`storage/db.py` persiste ticks/cotations ; `paper/c3_observer.py` capture les features
T0 puis une première cotation admissible entre 15 et 30 secondes. `paper/live.py`
et `executor.py` fournissent des primitives PAPER, sans entrée C3 automatique.
`strategies/` contient les primitives des quatre hypothèses. `analysis/bonereaper/`
est une recherche séparée sur les transactions publiques ; `_archive/` conserve
l'ancien scaffold. Les backtests portefeuille C3 évoluent de la seule LEG1 vers
le financement des deux jambes, l'immobilisation jusqu'à expiration et les pertes
des jambes non couvertes en V4. Les tests backend couvrent carnets et découverte ;
le test Phase A à la racine référence une ancienne architecture absente.

Les modifications préexistantes du backend et les résultats C3 sont conservés.
Les fichiers de résultats historiques OOS ne sont pas lus pour choisir D4.

## Périmètre et séparation

- Snapshot SQLite cohérent, source ouverte en lecture seule ; empreintes archivées.
- Slugs stricts `btc-updown-(5m|15m)-<timestamp>`, condition_id unique par marché.
- 60/20/20 chronologique par premier timestamp du marché, tous les marchés réels,
  avant filtrage D3. Même ordre que le manifeste C3 V2.1 existant obligatoire.
- D3 immuable : 5m, DOWN->UP, first_ask <= 0.14, hedge 15–30 s,
  friction 0.005 USDC par share appariée, budget LEG1 nominal 10, capital 500.
- Seules les features T0 sont accessibles au filtre. Les seuils candidats sont
  les quartiles TRAIN, jamais des quantiles VALIDATION ou OOS. Pas de nouvelle
  optimisation de first_ask, direction, durée, délai, budget ou friction.
- Filtres univariés sur les autres features proposées, et trois variables T0
  explicables : profondeur opposée / quantité LEG1 demandée, financement total
  estimé au carnet T0, capacité de sortie au bid T0 / quantité LEG1 demandée.
- Maximum trois seuils par feature, deux sens, plus couverture T0 >= 1 et >= 2.
  Aucune recherche de conjonctions après consultation des résultats.
- Filtre avant cooldown causal de 15 s par marché ; choix du premier timestamp,
  jamais du meilleur hedge futur. Valeur manquante : filtre rejeté, pas d'imputation.

## Sélection prédéfinie

TRAIN : au moins 20 marchés tradés, 50 trades, PnL > 0, PnL sans le meilleur
marché > 0, au moins 50 % des marchés tradés positifs, hedge complet >= 80 %,
hedge impossible <= 5 %, drawdown relatif <= 20 %. Le taux de hedge complet
doit également dépasser ou égaler celui de D3 sans filtre dans la même partition.
Ces critères doivent tenir avec sortie proxy V4 ET récupération nulle des résidus.
Classement TRAIN : PnL en stress, taux complet, nombre de marchés, ordre du candidat.
Un seul candidat TRAIN est présenté à VALIDATION. Même critères, sauf minimum
5 marchés / 20 trades. Aucun repêchage si ce candidat échoue.

Si aucun candidat ne passe, décision définitive NO EDGE / aucune entrée ; OOS
reste fermé car aucune règle de trading ne justifie sa consommation. Le résultat
du portefeuille d'abstention est exactement 500 -> 500, sans être un backtest OOS.
Sinon règle et empreintes figées avant une seule ouverture OOS ; un marqueur
exclusif interdit une seconde ouverture par le script. Les mêmes deux scénarios
sont exécutés lors de cette ouverture unique, sans changer la règle.

## Simulation et labels

V4 original reste une référence importée sans modification. Le simulateur D4
reprend ses budgets, profondeur au meilleur prix, cash contraint, friction et
règlement des paires à expiration, mais traite LEG1 et LEG2 à leurs timestamps
respectifs. À timestamp égal : règlement, hedge, puis nouvelle entrée.
Pas de réserve LEG2 ajoutée rétrospectivement. Chaque trade, y compris un hedge
impossible, apparaît dans le ledger et dans le PnL de son marché.

Les prix/quantités futurs invalides ou post-expiration ne permettent aucun hedge ;
l'ancre reste dans les signaux et son coût n'est pas annulé. La sortie de la portion
non couverte est modélisée au moment de l'échec : proxy bid/quantité T0 comme V4,
puis scénario conservateur à récupération nulle. Toute quantité non vendue vaut
zéro ; aucune résolution directionnelle inventée. Les ventes sont des hypothèses,
pas des exécutions historiques prouvées. Le cash d'une vente simulée n'est crédité
qu'à sa date de sortie. Les paires sont payées uniquement à l'expiration.

Deux labels distincts : capacité future du carnet seul à couvrir la demande
nominale de 10 USDC (sans cash portefeuille), et statut effectif du portefeuille
(complet / réduit / impossible) avec motifs cash et profondeur séparés.
`second_ask`, `second_ask_qty`, timestamps de hedge et résultats servent seulement
à l'exécution/aux labels, jamais au filtre ou au dimensionnement LEG1.

Drawdown : cash + valeur certaine des paires, LEG1 en attente valorisée à zéro
(borne sévère, pas un mark-to-market). Le pourcentage utilise le pic précédant
chaque creux, pas le pic final. PnL marché inclut toute perte LEG1. Concentration :
part du meilleur marché dans les gains positifs et PnL hors meilleur marché.
Intervalles descriptifs par bootstrap de marchés, aucune indépendance des signaux
supposée. Comparaison des features par classe avec valeurs manquantes et quartiles.

## Limites qui interdisent de prétendre à une preuve causale

L'observateur ne persiste pas les ancres sans futur carnet valide : le taux
d'échec absolu n'est pas identifiable. Ses queues par durée peuvent traverser une
rotation ; l'identité du token LEG2 n'est pas enregistrée. Les bases brutes stockent
`market_id=5m/15m`, pas le vrai slug ; `poly_quotes` possède des token_id mais pas
de table d'association vérifiée token/condition/slug. Aucune reconstruction
autoritaire des ancres manquantes ou des sorties n'est possible à partir du seul
schéma inspecté. Les hypothèses de sortie sont donc exposées, pas dissimulées.

L'ancien OOS a déjà été évalué par C3 V2.1 et V4 : le garder scellé pour D4 ne le
rend pas vierge. Un résultat positif sur ce holdout historique ne suffirait pas
à prouver un edge prospectif. Analyse temporellement causale au sens absence de
look-ahead dans les décisions ; associations observées, pas effet causal identifié.
La promotion PAPER D4 reste interdite tant que ces limites de données/exécution
empêchent une validation réaliste, même si des chiffres conditionnels sont positifs.

## Correction de précontrôle, avant calcul des performances

Le premier lancement TRAIN s'est arrêté sur trois ancres post-expiration de
33 à 155 ms : le timestamp local de l'observateur suit la réception du snapshot.
Elles sont désormais exportées dans un audit et rejetées à T0, puisque
l'expiration est déjà connue, au lieu d'interrompre toute l'analyse.
Aucun résultat de performance n'avait encore été calculé, VALIDATION/OOS
n'avaient pas été chargés. Le manifeste initial et les empreintes de cette
correction sont conservés dans `preflight_correction.json`.
