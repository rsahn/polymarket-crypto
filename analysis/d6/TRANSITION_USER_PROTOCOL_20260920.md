Tu travailles sur la transition officielle D5 → D6.

CONTEXTE

La collecte prospective D5 a été arrêtée volontairement après environ 3 h 02
pour contrainte de stockage.

Elle n'a donc PAS atteint l'objectif initial de 24 h.

Ne jamais présenter ce dataset comme une validation 24 h.

La collecte était :

- SHADOW
- NO_TRADE
- capital virtuel 500 USDC
- aucun ordre
- aucun fill
- aucun inventaire

Le collecteur s'est terminé avec un statut brut FAILED/KeyboardInterrupt lié
à l'arrêt volontaire.

Le journal indique que les buffers ont été écrits.

L'audit qualité et les deux replays NoTrade doivent maintenant déterminer si
le dataset est exploitable.

============================================================
PHASE 1 — FINALISATION D5
============================================================

Termine l'audit qualité complet de la collecte.

Ne modifie pas les données brutes.

Ne corrige aucun timestamp.

Ne supprime aucune observation.

Ne relance pas le collector.

Vérifie au minimum :

SQLite integrity_check
foreign key violations

CROSS_MARKET_VIOLATIONS
POST_EXPIRY_ACCEPTED
MISSING_TOKEN_IDS

BOOK incomplets acceptés
timestamps régressifs acceptés
anchors ouvertes après arrêt

nombre total d'événements
nombre de BOOK
nombre de ticks BTC

nombre de marchés 5m distincts
nombre de marchés 15m distincts

rotations 5m
rotations 15m
reconnexions

gaps par feed
gaps par marché
couverture temporelle réelle

événements rejetés :
- duplicates
- incomplete books
- out-of-order
- post-expiry

évolution des mesures NTP pendant la collecte.

Documenter explicitement l'arrêt volontaire.

============================================================
PHASE 2 — REPLAY
============================================================

Exécute DEUX replays NoTrade indépendants sur exactement le même dataset.

Comparer :

- nombre d'événements lus
- nombre de décisions
- état final
- résultats complets
- empreinte SHA-256 des décisions
- empreinte SHA-256 des résultats

Les deux exécutions doivent être déterministes.

Si les empreintes divergent :

STOP.

D6_RESEARCH_ALLOWED = false.

Diagnostiquer uniquement.

============================================================
PHASE 3 — DÉCISION DATA QUALITY
============================================================

Créer une décision explicite :

D5_DATA_QUALITY = PASS / FAIL

PASS exige notamment :

- SQLite OK
- aucune contamination cross-market
- aucun événement post-expiration accepté
- identité marché/token cohérente
- aucune anchor ouverte résiduelle
- replay déterministe
- couverture suffisante pour une recherche exploratoire

IMPORTANT :

La collecte ne dure qu'environ 3 heures.

Même si PASS :

ne pas prétendre que cette fenêtre couvre tous les régimes de marché.

Qualifier le dataset de :

"prospective D5 short-window dataset"

et non :

"24h validated dataset".

============================================================
PHASE 4 — GEL DU DATASET
============================================================

Si DATA QUALITY = PASS :

figer le dataset.

Créer :

- SHA-256 de la DB
- manifeste de collecte
- heure début
- heure fin
- durée
- session_id
- schema_version
- code version/git state
- rapport qualité
- empreintes replay

À partir de ce moment :

aucune modification de la DB.

Toute analyse D6 doit travailler en lecture seule ou sur snapshot/copie contrôlée.

============================================================
PHASE 5 — BONEREAPER CONTEMPORAIN
============================================================

Seulement si D5_DATA_QUALITY = PASS.

Le rapport historique Bonereaper existe dans :

analysis/bonereaper_public/

Proxy vérifié :

0xeebde7a0e019a63e6b476eb425505b7b3e6eba30

Extraire maintenant l'activité publique Bonereaper couvrant EXACTEMENT la fenêtre
temporelle de la collecte D5, avec une petite marge uniquement pour reconstruire
l'inventaire initial si nécessaire.

Ne pas mélanger cette extraction avec l'étude historique précédente.

Créer un nouveau dossier :

analysis/d6/bonereaper_contemporary/

Conserver les réponses brutes + métadonnées + SHA-256.

Vérifier :

condition_id
token_id
market_slug
duration
timestamp
outcome
side
price
quantity
usdcSize
transaction/hash

Ne jamais inventer un fill.

============================================================
PHASE 6 — JOINTURE D5 ↔ BONEREAPER
============================================================

Utiliser les documents déjà préparés dans analysis/d6/.

Respecter JOIN_SPEC.md et FEATURE_SCHEMA.md.

IMPORTANT :

les timestamps Bonereaper ont une précision limitée.

Ne jamais fabriquer une précision sub-seconde inexistante.

Pour une opération Bonereaper horodatée T :

utiliser uniquement les informations D5 disponibles AVANT la borne temporelle
autorisée.

Aucun nearest-neighbor vers le futur.

Conserver explicitement l'incertitude temporelle.

La question est :

"Quel état public du marché existait avant/autour de cette opération ?"

et PAS :

"Quel écran exact voyait Bonereaper ?"

============================================================
PHASE 7 — D6 RESEARCH
============================================================

Seulement après réussite des phases précédentes.

Utiliser les hypothèses H1–H8 déjà préparées :

H1 inventory rebalancing
H2 price opportunity
H3 pair cost management
H4 BTC lead
H5 Polymarket microstructure
H6 residual directional exposure
H7 market age
H8 size policy

Tester également les NULL MODELS préparés.

Ne cherche pas à reproduire le profit de Bonereaper.

Ne cherche pas à rendre artificiellement une stratégie rentable.

============================================================
PHASE 8 — PARTITIONS
============================================================

Partitionner chronologiquement PAR market_slug.

Aucun slug partagé.

Vu la fenêtre courte, rapporte le nombre exact de marchés avant de choisir les
proportions.

Utiliser :

TRAIN
VALIDATION
OOS

OOS ne doit JAMAIS servir au choix des features, règles, seuils ou modèles.

Si le nombre de marchés est insuffisant pour une séparation statistiquement
défendable :

STOP.

Ne pas inventer une validation.

Conclure :

INSUFFICIENT_DATA_FOR_OOS

et préparer directement la collecte/Paper prospectif nécessaire.

============================================================
PHASE 9 — STRATÉGIES CANDIDATES
============================================================

Préparer deux familles :

BONEREAPER_LIKE

et

D6_OPTIMIZED

BONEREAPER_LIKE cherche à reproduire les propriétés comportementales observées.

D6_OPTIMIZED cherche une politique indépendante potentiellement meilleure.

Aucune obligation pour D6_OPTIMIZED d'imiter Bonereaper.

Décisions possibles :

WAIT
BUY_UP
BUY_DOWN
REDUCE_UP
REDUCE_DOWN

Chaque décision doit être entièrement déterministe à partir de l'état causal.

============================================================
PHASE 10 — BACKTEST PORTEFEUILLE
============================================================

Capital initial :

500 USDC

Le replay doit être strictement chronologique.

Respecter :

cash réel simulé
profondeur disponible
fills partiels
frais
slippage
inventaire UP/DOWN
paired inventory
directional residual
settlement
capital immobilisé
latence configurable

INTERDICTIONS :

cash < 0
double consommation de liquidité
remboursement magique d'un mauvais trade
utilisation d'un prix futur
utilisation du résultat final comme feature
mélange entre marchés
réutilisation prématurée du capital

============================================================
PHASE 11 — MÉTRIQUES
============================================================

Pour chaque candidat :

capital initial
capital final
PnL
return %

max drawdown

marchés tradés
marchés gagnants/perdants

orders
fills
fill rate

UP qty
DOWN qty
paired qty

average pair cost

directional exposure
max directional exposure

time unhedged

fees
slippage

capital utilization
turnover

PnL par marché

profit concentration

résultat hors meilleur marché

stabilité chronologique

============================================================
PHASE 12 — CHALLENGE DU RÉSULTAT
============================================================

Si un résultat est très élevé, ne pas le rejeter.

Mais vérifier systématiquement :

look-ahead
timestamp leakage
cross-market contamination
double liquidity consumption
capital reuse
fees
slippage
settlement
inventory risk
PnL concentration
market dependence
multiple testing
latency assumptions

Le but est de déterminer si le résultat est véritable.

============================================================
PHASE 13 — DÉCISION PAPER
============================================================

À la fin, produire UNE des décisions suivantes :

NO_EDGE

INSUFFICIENT_DATA

CANDIDATE_NEEDS_MORE_VALIDATION

PAPER_READY

PAPER_READY exige :

- D5 quality PASS
- stratégie complètement figée
- aucune fuite temporelle
- résultat TRAIN acceptable
- résultat VALIDATION acceptable
- OOS positif et suffisamment représentatif
- modèle d'exécution réaliste
- résultat non dépendant d'un nombre minuscule de marchés
- drawdown acceptable
- aucune anomalie comptable

Si PAPER_READY :

NE PAS lancer automatiquement le Paper.

Préparer uniquement le moteur/configuration PAPER LIVE :

capital virtuel = 500 USDC

durée initiale prévue = 24 h

aucune clé privée

aucun endpoint d'envoi d'ordre réel

aucun passage LIVE possible automatiquement.

Attendre mon autorisation explicite avant démarrage du Paper.

============================================================
LIVRABLE FINAL
============================================================

Créer :

analysis/d6/FINAL_REPORT.md

avec :

1. verdict qualité D5
2. caractéristiques exactes du dataset
3. extraction Bonereaper contemporaine
4. qualité de la jointure
5. résultats H1–H8
6. modèles nuls
7. stratégie retenue éventuelle
8. TRAIN
9. VALIDATION
10. OOS
11. backtest portefeuille 500
12. drawdown
13. concentration
14. limites
15. décision finale :
    NO_EDGE /
    INSUFFICIENT_DATA /
    CANDIDATE_NEEDS_MORE_VALIDATION /
    PAPER_READY

IMPORTANT :

La priorité n'est pas d'arriver à PAPER_READY.

La priorité est d'obtenir le verdict correct.

Aucun ordre réel.
Aucun passage LIVE.
Aucune suppression des données D5.