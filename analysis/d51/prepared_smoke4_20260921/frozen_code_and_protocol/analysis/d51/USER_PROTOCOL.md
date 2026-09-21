Tu poursuis AUTONOMEMENT le projet D5 → D6.

Le verdict D5 actuel est officiellement :

D5_DATA_QUALITY = FAIL

NE JAMAIS modifier, réinterpréter ou remplacer ce verdict.

La collecte historique reste une preuve immuable de ce qui s'est produit.

============================================================
ÉTAT VALIDÉ À CONSERVER
============================================================

Dataset historique :

- durée utile ~3 h 02 min
- 7 518 713 événements
- 7 441 212 BOOK
- 66 517 BTC
- 38 marchés 5m
- 13 marchés 15m

Contrôles PASS :

- SQLite integrity_check = OK
- foreign_key_check = 0 violation
- CROSS_MARKET_VIOLATIONS = 0
- POST_EXPIRY_ACCEPTED = 0
- MISSING_TOKEN_IDS = 0
- open anchors = 0
- availability regressions = 0
- receive regressions = 0
- deux replays NoTrade complets
- mêmes décisions
- mêmes résultats
- mêmes états finaux
- capital 500
- zéro ordre/fill/inventaire

Empreintes :

decisions :
6184bfe7562e14867bd18789f315bedd7d15d613662c1a948a13ef828d1cdaa7

results :
00d76b967afeae5406afd09dabe1265550e6218f0bf67e13732a53c932ee9752

============================================================
CAUSES DU FAIL À TRAITER
============================================================

Le FAIL actuel provient notamment de :

1. ACCEPTED_TIMESTAMP_REGRESSION_BOOK_SOURCE

744 régressions du timestamp source de l'enveloppe BOOK.
Maximum observé : 507 ms.

Les timestamps propres aux côtés BOOK restent non décroissants.

Le diagnostic suggère que l'enveloppe utilise le timestamp du dernier message,
alors que les côtés possèdent leur propre metadata.

NE PAS corriger rétroactivement l'ancienne DB.

Définir explicitement le nouveau contrat temporel.

Déterminer quel timestamp représente :

- l'enveloppe
- UP
- DOWN
- source
- réception
- disponibilité

Éviter qu'un changement last_trade_price / price_change fasse apparaître
artificiellement une régression de l'état BOOK.

Ajouter tests synthétiques.

============================================================

2. GAPS > 5 SECONDES

Historique :

5m : 10
15m : 3
BTC : 2

maximum : 8,557 s.

Diagnostic existant :

- 6 gaps correspondent à des transitions entre marchés 5m
- 7 sont internes à un marché
- 2 concernent BTC

NE PAS modifier rétroactivement le seuil de l'ancienne expérience.

Pour le NOUVEAU protocole :

distinguer explicitement :

TRANSITION_GAP
INTERNAL_FEED_GAP
RECONNECT_GAP
STARTUP_GAP
SHUTDOWN_GAP

Un changement normal de marché ne doit pas être automatiquement assimilé
à une perte de feed.

En revanche, un véritable trou interne doit rester visible et être traité
conservativement.

Ajouter des tests de rotation 5m/15m.

============================================================

3. UNCLEAN_STOP

La collecte historique a été volontairement interrompue mais son wrapper a
conservé :

FAILED / KeyboardInterrupt

alors que :

COLLECTION_STOP existe
SESSION_END existe
open anchors = 0
SQLite = OK
FK = OK

Corriger le superviseur pour qu'un arrêt utilisateur volontaire et propre
produise un statut distinct, par exemple :

STOPPED_BY_USER_CLEAN

ou équivalent.

Ne jamais convertir l'ancien statut historique.

Ajouter test d'arrêt propre.

============================================================

4. HORLOGE / W32TIME

Le gate 100 ms avait été explicitement autorisé avant la collecte.

Les sondes NTP respectaient ce seuil au lancement.

Mais W32Time a ensuite indiqué une erreur de synchronisation liée à des données
obsolètes.

Pour la prochaine collecte :

ne pas se contenter du statut W32Time.

Conserver :

- deux références NTP indépendantes
- plusieurs mesures par référence
- offset
- dispersion
- timestamp des mesures
- état W32Time
- source W32Time
- dernière synchro
- erreur W32Time

Définir explicitement les conditions acceptables AVANT la collecte.

Ne jamais recaler les timestamps historiques.

============================================================
OBJECTIF IMMÉDIAT
============================================================

NE PAS refaire immédiatement 3 h.

Construire d'abord D5.1 :

"corrected prospective validation collector"

Corriger uniquement les problèmes démontrés.

Ne pas modifier les règles simplement pour obtenir PASS.

Ajouter les tests nécessaires.

Exécuter toute la suite de tests existante + nouveaux tests.

============================================================
SMOKE PROSPECTIF
============================================================

Lorsque D5.1 est prêt :

lancer automatiquement une NOUVELLE collecte prospective courte.

Durée cible :

20 minutes minimum.

Nouvelle DB exclusivement.

Ne jamais réutiliser ou modifier l'ancienne DB.

Mode :

SHADOW
NO_TRADE
capital virtuel 500

Aucun ordre.
Aucun fill.
Aucun inventaire.
Aucune clé privée.
Aucun wallet.

Pendant le smoke :

- 5m actif
- 15m actif
- BTC actif
- au moins plusieurs rotations 5m si la fenêtre le permet
- observer reconnexion si elle se produit naturellement
- ne pas provoquer artificiellement une panne réseau uniquement pour obtenir
  une reconnexion

============================================================
AUDIT D5.1
============================================================

Après arrêt propre du smoke :

exécuter automatiquement la nouvelle chaîne instrumentée.

Vérifier :

SQLite integrity
foreign keys
cross-market
post-expiry
missing tokens
open anchors
timestamp contract
feed gaps
rotations
reconnections
NTP evidence
clean stop
provenance
Replay #1
Replay #2
hashes identiques

Utiliser l'auditeur optimisé/checkpointé.

Afficher progression X/N.

Ne pas imposer de timeout destructif tant que le processus progresse.

============================================================
SI LE SMOKE FAIL
============================================================

Diagnostiquer automatiquement.

Si le problème vient du code :

corriger
tester
relancer un NOUVEAU smoke.

Tu peux répéter ce cycle automatiquement :

CODE
↓
TESTS
↓
NEW SMOKE
↓
AUDIT
↓
FAIL
↓
DIAGNOSTIC
↓
FIX

jusqu'à obtenir un résultat méthodologiquement valide
OU découvrir un problème nécessitant réellement une décision utilisateur.

Ne jamais assouplir silencieusement un critère pour obtenir PASS.

============================================================
SI LE SMOKE PASS
============================================================

Ne considère pas 20 minutes comme une validation statistique suffisante de D6.

Le smoke valide l'INSTRUMENTATION.

Ensuite décider automatiquement d'une collecte D5.1 plus longue mais raisonnable.

Objectif :

obtenir suffisamment de marchés indépendants pour D6 sans reproduire inutilement
les dizaines de Go de D5.

Utiliser les enseignements Parquet/DuckDB pour réduire le stockage si cela peut
être fait SANS perte des données nécessaires à :

- microstructure
- replay
- profondeur
- BTC
- jointure causale
- audit

Ne supprimer aucune information nécessaire uniquement pour économiser de l'espace.

Si une nouvelle collecte longue est nécessaire, utiliser une nouvelle DB/dataset.

============================================================
ANCIEN DATASET D5
============================================================

NE PAS LE JETER.

Le conserver pour :

- développement
- tests
- diagnostics
- analyse exploratoire clairement étiquetée
- comparaison des corrections
- recherche de causes des gaps

Mais :

NE PAS l'utiliser comme dataset homologué TRAIN/VALIDATION/OOS tant que son
statut reste FAIL.

============================================================
PASS → D6
============================================================

Lorsque nous disposons d'un dataset prospectif admissible :

enchaîner automatiquement D6.

Utiliser :

- nouvelle collecte D5.1 validée
- données publiques Bonereaper
- ancien rapport Bonereaper comme hypothèses descriptives
- BTC
- carnet Polymarket
- microstructure
- inventaire lorsque reconstructible

Tester :

H1 inventory rebalancing
H2 price opportunity
H3 pair cost management
H4 BTC lead
H5 Polymarket microstructure
H6 directional residual
H7 market age
H8 size policy

Comparer également :

ancienne stratégie C3
BONEREAPER_LIKE
D6_OPTIMIZED
NULL MODELS

============================================================
VALIDATION D6
============================================================

Respect obligatoire :

TRAIN
↓
VALIDATION
↓
STRATEGIE FIGÉE
↓
OOS OUVERT UNE SEULE FOIS

Aucun slug partagé.

Aucun ajustement après lecture OOS.

Si l'échantillon est insuffisant :

ne pas inventer de significativité.

Utiliser le futur PAPER comme validation prospective supplémentaire.

============================================================
PAPER
============================================================

Préparer PAPER500 pour :

capital virtuel = 500 USDC

durée prévue = 72 heures

stratégie complètement figée

dashboard dynamique

checkpoints :

24 h
48 h
72 h

NE PAS lancer PAPER sans mon autorisation explicite.

Le dernier état autonome autorisé est :

PAPER500_READY_FOR_USER_APPROVAL

============================================================
INTERDICTIONS ABSOLUES
============================================================

Aucun LIVE.

Aucun ordre réel.

Aucune clé privée.

Aucun wallet.

Aucun transfert de fonds.

Aucune signature blockchain.

Aucune modification de l'ancienne DB.

Aucune suppression des preuves.

Aucune correction rétroactive des timestamps.

Aucun assouplissement opportuniste des critères.

Aucune ouverture prématurée de l'OOS.

============================================================
AUTONOMIE
============================================================

Tu es autorisé à :

diagnostiquer
modifier le code
tester
optimiser
relancer
faire de nouveaux smokes
auditer
corriger les outils
checkpoint/reprendre
préparer D6
exécuter TRAIN/VALIDATION/OOS lorsque le dataset est admissible

sans demander confirmation pour les opérations techniques normales.

Ne me sollicite que si :

- une décision méthodologique réellement ambiguë est nécessaire ;
- une donnée brute devrait être modifiée/supprimée ;
- une action irréversible est nécessaire ;
- un défaut réel empêche de poursuivre ;
- PAPER500_READY_FOR_USER_APPROVAL est atteint.

============================================================
PRINCIPE FINAL
============================================================

Ne cherche pas à transformer le FAIL historique en PASS.

Utilise ce FAIL pour construire une meilleure expérience prospective.

La priorité est :

DATA CORRECT
→ STRATEGY CORRECT
→ PAPER PROSPECTIF

et non :

PASS À TOUT PRIX.

Commence maintenant et poursuis de manière autonome.