# D5 — horloge Windows et préparation de la collecte prospective

> Mise à jour : synchronisation système autorisée et W32Time actif. Le lancement autonome attend la convergence NTP mesurée ; voir [SYNC_AND_LAUNCH_STATUS.md](clock_sync_20260920_091052/SYNC_AND_LAUNCH_STATUS.md). Le statut de décision ci-dessous est historique.

État au 20 septembre 2026 : préparation technique terminée ; collecte de
production 24 h NON DÉMARRÉE, en attente de la décision de synchronisation Windows.

## Horloge : constat et origine probable des deltas négatifs

`Get-Service W32Time` retourne Stopped, démarrage Manual. Les commandes
`w32tm /query /status /verbose` et `/query /configuration` échouent avec
0x80070426 (service non démarré). La synchronisation Windows ne peut donc pas
être attestée.

Mesures sans réglage de l’horloge, le 20 septembre vers 08:53 locale :

- time.windows.com : +0,5954145 ; +0,5874015 ; +0,5957680 ; +0,5878881 ; +0,5896683 s.
- time.cloudflare.com : +0,5928993 ; +0,5927138 ; +0,5924554 ; +0,5951774 ; +0,5950898 s.

Ces deux références indépendantes concordent : l’horloge locale retarde
d’environ 0,59 seconde. Un second relevé vers 09:03 confirme cet ordre de grandeur
(`preflight_20260920_090339/clock_before.json`).

La différence enregistrée est `réception locale - timestamp source`. Elle combine
le délai réseau/traitement et la différence entre les horloges. Un retard local
peut donc produire une différence négative. Le retard mesuré explique probablement
les moyennes du smoke précédent (-339 ms BOOK, -312 ms BTC). Il ne prouve pas
l’offset exact des serveurs Polymarket/Binance au moment du smoke : les relevés
NTP ont été faits plus tard et l’horloge source n’a pas été mesurée directement.

L’inspection du code confirme des timestamps Unix en millisecondes : Binance
conserve E et Polymarket conserve timestamp/event_ts_ms ; la réception provient
de l’horloge locale. L’ordre de grandeur observé n’évoque pas une confusion
secondes/millisecondes ou un décalage de fuseau horaire. Ce ne sont pas des
latences réseau physiques négatives.

Documentation Microsoft :
https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings
`/stripchart` mesure l’offset ; `/resync` demande une synchronisation et modifie
l’horloge système. Aucune synchronisation ni correction de timestamps n’a été
appliquée durant cette préparation.

## Superviseur préparé

Point d’entrée : `backend/run_d5_24h.py` (implémentation `app/d5/prospective.py`).
Le lancement de production crée exclusivement une base nommée
`d5_live_24h_YYYYMMDD_HHMMSS.db`. Un nom existant est refusé. Durée prévue :
86 520 secondes (24 h 2 min), pour permettre la couverture complète des feeds
après découverte/connexion. Le seuil de revue reste au moins 86 400 secondes de
collecte ET de couverture pour chacun des feeds 5m, 15m et BTC.

- SHADOW, NO_TRADE, capital virtuel 500 ; aucun ordre, fill ou inventaire.
- Processus Windows détaché, fenêtre masquée ; demande temporaire de maintien
  d’éveil, libérée à la fin. L’ordinateur doit rester allumé et alimenté ; aucune
  promesse de résistance à une extinction/reboot ou fermeture forcée du système.
- Rotations 5m/15m et reconnexions gérées par le collecteur ; les rotations sont
  aussi journalisées comme événements explicites.
- État `status.json` actualisé toutes les 30 s ; événements CLOCK_SAMPLE avec
  horloge murale et monotone brutes ; mesures NTP avant, toutes les heures et après.
- Réserve disque 5 Gio : arrêt propre et état FAILED si elle est atteinte.
  Aucune suppression automatique de base pour gagner de l’espace.
- Arrêt demandé au terme de la durée ; la durée d’acquisition est distinguée du
  temps de fermeture des sockets, sans changer les timestamps source/réception.
- Après fermeture du writer seulement : DATA QUALITY REPORT puis deux replays
  NoTrade, empreintes SHA-256 des décisions ET des résultats complets, sans
  conserver en mémoire l’ensemble des décisions.
- Aucune recherche/optimisation/backtest pendant la collecte. Aucun D5 Research
  après la revue : RESEARCH_ALLOWED reste false ; réussite de la revue est une
  condition nécessaire, pas une autorisation de démarrer la recherche.

Le rapport fournit durée réelle, nombres d’événements et de marchés distincts,
rotations, reconnexions, gaps par marché et par feed incluant les transitions,
CROSS_MARKET_VIOLATIONS, POST_EXPIRY_ACCEPTED, MISSING_TOKEN_IDS, rejets/hors ordre,
SQLite integrity_check, clés étrangères, ancres ouvertes, résultats des deux
replays et égalité de leurs empreintes. Tout gap >5 s ou extrémité >10 s est
signalé pour revue, sans être effacé ou automatiquement excusé. L’absence de
reconnexion n’est pas une anomalie : sa résistance a déjà été validée au smoke.

## Espace disque et conservation

Environ 151 Go décimaux libres avant préparation. Le débit du smoke non compressé
pouvait dépasser cette capacité en 24 h. Le nouveau dossier
`data/d5_24h_20260920_085530` utilise une compression NTFS transparente. Un schéma
D5 v2 réservé aux nouvelles bases compresse en plus les grands JSON par zlib
sans perte ; les colonnes de timestamps et de prix/quantités sont conservées
numériquement. `decode`/`json_text` restituent exactement les JSON ; audit et replay
acceptent v1 et v2. Aucun schéma historique n’est migré, aucun timestamp recalé.

Le test détaché de 20 s a utilisé 44 687 360 octets logiques et environ
27 549 696 octets physiques, soit une projection indicative de 111 Gio/24 h à ce
débit. Le trafic peut varier : ce chiffre n’est pas une garantie. La réserve et
la supervision surveilleront l’espace disponible.

## Tests de préparation

- 45 tests backend réussis (`prospective_preflight_tests.log`).
- Test détaché `preflight_20260920_090339` : 14 435 événements, dont 14 289 BOOK ;
  SQLite ok, zéro ancre ouverte, zéro ordre/fill/inventaire, deux replays identiques.
  Il reste explicitement un test de 20 s, pas une validation 24 h.
- Ce test a mis en évidence 10 s de fermeture de sockets : instrumentation
  améliorée par un événement COLLECTION_STOP distinct de SESSION_END ; test
  de régression ajouté pour éviter de comptabiliser ce temps comme un gap de feed.
- Tests de refus d’écrasement d’ancienne base, conversion silencieuse v1/v2,
  identité/expiration, compression réversible et statut FAILED en cas d’erreur.

## Décision système en attente

Question envoyée : autorisation de démarrer Windows Time puis de demander une
synchronisation NTP normale avant le lancement, ou conservation de l’horloge avec
écart documenté. Cette décision concerne l’horloge Windows, pas une correction
artificielle des données. Aucun timestamp historique ne sera modifié dans les
deux cas. Le suivi automatique sera attaché à la collecte effectivement lancée.
