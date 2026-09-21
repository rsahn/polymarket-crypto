# MISSION PRINCIPALE — D6 PAPER LIVE 500 USDC

Tu travailles dans :

C:\Users\Ramy\Documents\polymarket-crypto

PRIORITÉ ABSOLUE DU PROJET :

ARRIVER AU PREMIER PAPER TRADING LIVE D6 AVEC 500 USDC VIRTUELS.

Nous avons suffisamment construit l'infrastructure de recherche.

À partir de maintenant :

- ne crée pas D7, D8 ou D9 ;
- ne reconstruis pas inutilement l'architecture ;
- ne transforme pas chaque incertitude en plusieurs heures de développement ;
- réutilise D5, D6 et l'analyse Bonereaper existants ;
- privilégie l'expérimentation prospective PAPER.

Le Paper fait partie de la validation.

============================================================
0 — SÉCURITÉ ABSOLUE
============================================================

PAPER UNIQUEMENT.

INTERDIT :

- argent réel ;
- ordre réel Polymarket ;
- signature wallet ;
- clé privée ;
- seed phrase ;
- dépôt/retrait ;
- transfert de fonds ;
- endpoint create_order/post_order réel ;
- passage automatique PAPER -> LIVE.

Le moteur Paper doit techniquement être incapable d'envoyer un ordre réel.

Si une configuration contient :

LIVE_TRADING=true

ou équivalent :

RAISE EXCEPTION.

Capital Paper :

500 USDC VIRTUELS.

Aucune action réelle.

============================================================
1 — CONTEXTE D5
============================================================

D5 a effectué une collecte prospective d'environ 3 heures.

La base est CLOSE.

Elle contient plusieurs millions d'événements carnet réels Polymarket,
BTC réel et les informations nécessaires à la reconstruction temporelle.

Le collecteur n'écrit plus dans cette base.

La DB brute D5 doit rester IMMUTABLE.

NE PAS :

- modifier la DB ;
- VACUUM ;
- réécrire des timestamps ;
- supprimer des observations ;
- migrer la DB historique ;
- relancer la collecte D5 actuelle.

Un ancien audit D5 est encore susceptible de tourner séparément.

NE PAS tuer ou modifier son processus.

Son résultat devra être conservé.

Cependant :

L'AUDIT HISTORIQUE NE DOIT PLUS BLOQUER LE DÉVELOPPEMENT DU PAPER.

Si son verdict final détecte ensuite une anomalie critique susceptible
d'invalider la stratégie :

le Paper ne doit pas démarrer.

============================================================
2 — PROBLÈME D'ARCHITECTURE À CORRIGER
============================================================

L'ancien pipeline analytique rescannait une DB SQLite de plusieurs dizaines
de Go à répétition.

Cela a produit des centaines de Go de lectures et plusieurs heures d'audit.

Ce fonctionnement n'est pas acceptable pour la recherche quantitative
interactive.

SQLite peut rester utilisé pour :

- sessions ;
- état opérationnel ;
- inventaire Paper ;
- décisions ;
- fills simulés ;
- journalisation légère.

Mais les analyses massives doivent utiliser un format analytique adapté.

============================================================
3 — DATA PIPELINE RAPIDE
============================================================

Construire un pipeline séparé :

D5 SQLite RAW
      |
      | READ ONLY
      v
Extraction en aussi peu de parcours que possible
      |
      v
PARQUET
      |
      v
DUCKDB
      |
      v
D6 FEATURES
      |
      v
RESEARCH / REPLAY / PAPER PREPARATION

La DB D5 originale ne doit jamais être modifiée.

Créer par exemple :

analysis/d6/data/

raw_manifest.json
parquet/
d6.duckdb
conversion_report.json

Partitionner intelligemment si utile :

market_duration
market_slug
date

Éviter les JSON redondants lorsque les mêmes champs existent déjà
structurellement.

Conserver cependant toutes les informations nécessaires pour reconstruire
une décision.

============================================================
4 — OBJECTIF PERFORMANCE
============================================================

Je ne veux plus plusieurs heures d'attente pour une analyse ordinaire.

Objectif :

conversion + contrôles essentiels + features principales
< 60 minutes si techniquement raisonnable.

Ne falsifie aucun contrôle pour respecter cette durée.

Mesurer :

temps conversion
taille source
taille Parquet
nombre de lignes
débit
mémoire
temps des requêtes D6
espace disque.

Toutes les longues opérations doivent afficher une progression réelle :

[1/8] Extraction BOOK ........ 42%
[2/8] BTC .................... WAITING
...

Ne jamais inventer un pourcentage.

============================================================
5 — CONTEXTE BONEREAPER
============================================================

Rapport existant :

analysis/bonereaper_public/REPORT.md

Proxy public vérifié :

0xeebde7a0e019a63e6b476eb425505b7b3e6eba30

Principaux faits historiques BTC 5m :

- 1 982 marchés analysés ;
- 62 200 lignes TRADE ;
- 97,68 % des marchés avec achats UP ET DOWN ;
- médiane 28 fills API par marché ;
- médiane 9 secondes entre legs opposés ;
- accumulation progressive fréquente ;
- alternance UP/DOWN fréquente ;
- inventaire souvent fortement déséquilibré ;
- coût de paire variable ;
- aucune règle universelle pair_cost < 1 ;
- seulement une partie des nouveaux achats réduit l'imbalance ;
- comportement 15m très différent du 5m.

IMPORTANT :

Bonereaper est une SOURCE D'HYPOTHÈSES.

Il n'est PAS une stratégie à copier aveuglément.

============================================================
6 — BONEREAPER CONTEMPORAIN
============================================================

Extraire séparément l'activité publique Bonereaper correspondant exactement
à la fenêtre temporelle D5.

Créer :

analysis/d6/bonereaper_contemporary/

Conserver :

raw responses
metadata
SHA-256
timestamp
market_slug
condition_id
token_id
duration
outcome
side
price
quantity
usdcSize
transaction/hash

Ne jamais inventer un fill.

Si l'inventaire initial est inconnu :

UNKNOWN.

Ne jamais le compléter artificiellement.

============================================================
7 — JOINTURE D5 ↔ BONEREAPER
============================================================

Utiliser :

analysis/d6/JOIN_SPEC.md
analysis/d6/FEATURE_SCHEMA.md

Clés fortes :

condition_id
token_id
market_slug
market_duration

IMPORTANT :

l'activité Bonereaper possède une précision temporelle limitée.

Ne jamais fabriquer une précision sub-seconde inexistante.

Pour un événement Bonereaper à T :

features = données disponibles AVANT la borne temporelle autorisée.

Aucun nearest-neighbor tourné vers le futur.

La question correcte est :

"Quel état public du marché existait avant/autour de cette opération ?"

PAS :

"Quel écran exact voyait Bonereaper ?"

============================================================
8 — D6 RESEARCH
============================================================

Utiliser les documents déjà créés :

RESEARCH_PROTOCOL.md
FEATURE_SCHEMA.md
HYPOTHESES.md
NULL_MODELS.md
JOIN_SPEC.md
EXECUTION_MODEL.md
VALIDATION_PROTOCOL.md

Ne lance pas une optimisation exhaustive de milliers de paramètres.

Commencer par des mécanismes simples, interprétables et causaux.

============================================================
9 — HYPOTHÈSES PRIORITAIRES
============================================================

H1 — INVENTORY REBALANCING

Est-ce que l'état de l'inventaire explique l'achat du prochain côté ?

H2 — PRICE OPPORTUNITY

Un outcome devient-il intéressant relativement au coût moyen déjà détenu ?

H3 — PAIR COST MANAGEMENT

Certains achats améliorent-ils le coût moyen combiné ?

H4 — BTC LEAD / MOMENTUM

Un mouvement BTC strictement antérieur explique-t-il le côté acheté ?

H5 — POLYMARKET MICROSTRUCTURE

Spread, profondeur ou imbalance expliquent-ils timing/côté ?

H6 — RESIDUAL DIRECTIONAL EXPOSURE

Le résidu UP/DOWN est-il lié à un signal observable ?

H7 — MARKET AGE

Le comportement dépend-il :

avant fenêtre
premier tiers
milieu
dernier tiers ?

H8 — SIZE POLICY

La quantité dépend-elle :

signal
liquidité
depth
volatilité
imbalance
temps restant
cash disponible ?

============================================================
10 — FEATURES
============================================================

BTC :

price
returns 250 ms
500 ms
1 s
3 s
5 s
10 s
15 s
30 s

local volatility
momentum
acceleration

POLYMARKET :

UP best_bid
UP best_ask
UP quantities

DOWN best_bid
DOWN best_ask
DOWN quantities

spread UP
spread DOWN

depth UP
depth DOWN

order-book imbalance
depth imbalance
liquidity ratio

executable pair ask cost

market age
time remaining

INVENTORY :

cash

up_qty
down_qty

average_up_cost
average_down_cost

paired_qty
average_pair_cost

directional_up
directional_down

inventory_imbalance

time_since_last_action
time_since_last_up
time_since_last_down
time_since_opposite_leg

============================================================
11 — ANTI-LOOKAHEAD ABSOLU
============================================================

features(T) utilisent uniquement information disponible <= T.

INTERDIT :

future BTC
future BOOK
future outcome
future settlement
future price
future inventory
future fill
nearest-neighbor futur.

Ajouter/maintenir tests synthétiques anti-lookahead.

============================================================
12 — NULL MODELS
============================================================

Comparer D6 à des règles triviales :

RANDOM SIDE

ALWAYS CHEAPER SIDE

ALWAYS REBALANCE

FIXED ALTERNATING

PAIR_COST_THRESHOLD

WAIT ONLY

Le modèle D6 doit apporter quelque chose de mesurable par rapport à ces
baselines.

============================================================
13 — PREMIER CANDIDAT D6
============================================================

Créer une stratégie déterministe.

Actions possibles :

WAIT
BUY_UP
BUY_DOWN
REDUCE_UP
REDUCE_DOWN

Ne pas imposer :

UP == DOWN.

Ne pas imposer :

pair_cost < 1

comme unique règle.

Autoriser un déséquilibre directionnel contrôlé.

Mais définir :

max directional exposure
max capital per market
max order size
max drawdown Paper
minimum liquidity
minimum cash reserve.

============================================================
14 — TRAIN / VALIDATION / OOS
============================================================

Séparer chronologiquement PAR market_slug.

Aucun slug partagé.

TRAIN :
découverte.

VALIDATION :
sélection.

OOS :
ouverture une seule fois si effectif suffisant.

Ne jamais modifier la stratégie après avoir observé OOS.

IMPORTANT :

la fenêtre D5 est courte.

Si OOS statistiquement insuffisant :

NE PAS BLOQUER INDÉFINIMENT LE PROJET.

Autoriser :

EXPERIMENTAL_PAPER_READY

Le Paper devient alors l'OOS prospectif principal.

============================================================
15 — BACKTEST PORTEFEUILLE
============================================================

Capital initial :

500 USDC.

Replay strictement chronologique.

Chaque BUY :

cash -= coût + frais.

Cash >= 0 toujours.

Maintenir :

cash
UP inventory
DOWN inventory
paired inventory
directional exposure
average costs
PnL
equity
drawdown.

Settlement uniquement lorsque le marché le permet.

Aucun capital libéré prématurément.

============================================================
16 — EXECUTION MODEL
============================================================

Les fills doivent respecter la profondeur réellement disponible.

Exemple :

BUY UP requested = 20

ASK :

13 @ 0.42
7 @ 0.43

Fill :

13 @ 0.42
7 @ 0.43

VWAP calculé réellement.

Enregistrer :

requested_qty
filled_qty
VWAP
notional
fees
slippage.

INTERDIT :

double consommation de liquidité
fill > depth
cash négatif
cross-market fill
prix futur.

============================================================
17 — LATENCE
============================================================

Préparer une latence configurable.

Évaluer :

0 ms référence optimiste
100 ms
250 ms
500 ms

La stratégie Paper choisie doit utiliser une hypothèse documentée et
raisonnable.

Ne pas sélectionner une stratégie uniquement parce qu'elle fonctionne à
0 ms.

============================================================
18 — CHALLENGE DU RÉSULTAT
============================================================

Si le backtest produit un résultat énorme :

NE PAS le rejeter automatiquement.

Mais vérifier :

look-ahead
cross-market contamination
future timestamps
double liquidity consumption
capital reuse
fees
slippage
settlement
inventory risk
PnL concentration
market dependence
multiple testing
latency sensitivity.

Le but est de savoir si le résultat est vrai ou artificiel.

Ne transforme pas cette étape en plusieurs jours de développement.

============================================================
19 — VERDICT OFFLINE
============================================================

Verdicts autorisés :

NO_CANDIDATE

EXPERIMENTAL_PAPER_READY

PAPER_READY

WAITING_FOR_D5_AUDIT

EXPERIMENTAL_PAPER_READY signifie :

"Les données historiques ne permettent pas encore une validation forte,
mais le système est techniquement suffisamment sûr pour une validation
prospective sans argent réel."

C'est un verdict acceptable.

============================================================
20 — PAPER LIVE
============================================================

Préparer :

D6 PAPER LIVE

Capital initial :

500 USDC virtuels.

Durée initiale :

24 heures.

La stratégie doit être FIGÉE avant lancement.

Pendant le Paper :

AUCUNE optimisation.

AUCUN changement de seuil.

AUCUN changement de features.

AUCUNE modification de stratégie.

Chaque marché rencontré est futur et inconnu au lancement.

============================================================
21 — PAPER = OOS PROSPECTIF
============================================================

Le Paper devient notre test de vérité principal avant argent réel.

À chaque instant :

marché réel
      |
      v
features causales
      |
      v
D6
      |
      v
BUY_UP / BUY_DOWN / WAIT / REDUCE
      |
      v
execution simulator
      |
      v
inventory
      |
      v
PnL

La stratégie ne connaît jamais le futur.

============================================================
22 — STOCKAGE PAPER
============================================================

NE PAS reproduire inutilement les ~100 Go/jour de D5.

Le Paper doit conserver suffisamment pour AUDITER chaque décision :

- contexte de marché nécessaire ;
- features ;
- décision ;
- carnet utilisé ;
- ordre simulé ;
- fill ;
- inventaire ;
- settlement ;
- PnL.

Stockage événementiel ciblé.

============================================================
23 — JOURNAL COMPLET
============================================================

Chaque décision doit permettre de reconstruire :

STATE BEFORE
FEATURES
DECISION
REASON
PAPER ORDER
SIMULATED FILL
STATE AFTER
SETTLEMENT
PnL.

Chaque événement doit contenir :

timestamp
market
condition
token
decision_id.

============================================================
24 — DASHBOARD TEMPS RÉEL
============================================================

Créer un dashboard local professionnel inspiré d'un terminal quant.

STYLE :

fond noir
accent magenta/violet
vert pour gains
rouge pour pertes
typographie terminal/quant
graphiques sobres
pas d'animations inutiles.

Affichage très clair :

D6 — BTC POLYMARKET

PAPER LIVE

NO REAL MONEY

============================================================
25 — HEADER DASHBOARD
============================================================

Afficher :

MODE : PAPER

Capital initial : 500.00

Equity actuelle

PnL USDC

PnL %

PnL today

Realized PnL

Unrealized PnL

Current drawdown

Max drawdown

Uptime

============================================================
26 — BTC PANEL
============================================================

Afficher :

BTC LIVE PRICE

courbe BTC

returns :
1s
5s
15s

volatility

momentum

feed latency

feed status.

============================================================
27 — POLYMARKET PANEL
============================================================

Marché actif :

BTC UP/DOWN 5M

market_slug
condition_id

time remaining

UP bid
UP ask
UP depth

DOWN bid
DOWN ask
DOWN depth

spread

pair ask cost

order-book imbalance.

============================================================
28 — INVENTORY PANEL
============================================================

Afficher :

UP shares
DOWN shares

Average UP cost
Average DOWN cost

Paired shares

Average pair cost

Directional UP
Directional DOWN

Inventory imbalance

Capital locked

Cash available.

============================================================
29 — D6 SIGNAL PANEL
============================================================

Afficher :

BTC momentum signal
microstructure signal
inventory signal
pair-cost signal

Final decision :

WAIT
BUY_UP
BUY_DOWN
REDUCE_UP
REDUCE_DOWN

Afficher également un score interne uniquement s'il existe réellement.

Ne pas inventer une "confidence IA".

============================================================
30 — EXECUTION PANEL
============================================================

Afficher les dernières actions :

timestamp
decision
requested qty
filled qty
fill price
VWAP
fees
slippage.

Exemple :

18:42:03 BUY_DOWN requested 20
18:42:03 FILLED 17 @ 0.342
18:42:04 PARTIAL 3 UNFILLED
18:42:08 WAIT

============================================================
31 — PERFORMANCE PANEL
============================================================

Afficher :

Markets seen
Markets traded

Winning markets
Losing markets

Win rate

PnL per market

Best market
Worst market

Average market PnL

Turnover

Capital utilization

Fees total

Slippage total.

============================================================
32 — EQUITY CURVE
============================================================

Afficher une courbe :

500 initial
   |
   v
equity live.

Ajouter :

drawdown curve

sans masquer les pertes.

============================================================
33 — AUDITABILITY
============================================================

Chaque chiffre du dashboard doit provenir :

- de l'état Paper ;
- du journal ;
- du feed ;
- du moteur d'exécution.

Aucune métrique décorative inventée.

Le dashboard est READ ONLY.

Aucun bouton BUY/SELL réel.

Aucun bouton LIVE.

============================================================
34 — FAILSAFE PAPER
============================================================

Le Paper doit s'arrêter proprement si :

feed Polymarket perdu durablement
feed BTC perdu durablement
clock anomaly importante
DB Paper inaccessible
état inventaire incohérent
cash < 0
cross-market détecté
exception critique.

Le dashboard doit afficher :

RUNNING
PAUSED
FAILED
COMPLETED

avec raison.

============================================================
35 — APRÈS 24 H
============================================================

À la fin du Paper produire automatiquement :

PAPER_24H_REPORT.md

avec :

Capital initial
Capital final

PnL
Return %

Max drawdown

Markets seen
Markets traded

Winning markets
Losing markets

Orders
Fills
Fill rate

Fees
Slippage

Turnover

Capital utilization

Average pair cost

Max directional exposure

Time unhedged

Best market
Worst market

PnL concentration

Performance par heure

Performance par régime

Latence observée

Feed failures

Toutes anomalies.

============================================================
36 — PAS DE MODIFICATION APRÈS COUP
============================================================

La stratégie utilisée pendant les 24 h doit être hashée avant lancement.

Créer :

STRATEGY_LOCK.json

avec :

version
parameters
features
code hash
timestamp.

Le rapport final doit confirmer que le hash n'a pas changé pendant
l'expérience.

============================================================
37 — APRÈS PAPER
============================================================

NE PAS passer