# D5 — collecte prospective lancée

La collecte de production est démarrée dans une NOUVELLE base :
`C:\Users\Ramy\Documents\polymarket-crypto\data\d5_24h_20260920_085530\d5_live_24h_20260920_124822.db`.

- Début de collecte (UTC) : 2026-09-20T10:48:27.240000+00:00.
- Fin prévue (UTC) : 2026-09-21T10:50:27.240024+00:00.
- Durée demandée : 86 520 secondes, soit 24 h 2 min.
- Session : `83b5cc8a-4592-4676-b28d-3da2ac6d0088` ; PID collecteur : 4920.
- SHADOW / NO_TRADE ; capital virtuel 500 ; aucun ordre/fill/inventaire.
- W32Time actif ; deux nouveaux contrôles NTP conformes au maximum inclusif
  de 100 ms sur chacune des mesures des deux références.
- Contrôle 1 : 45,505 à 53,6063 ms. Contrôle 2 : 51,0902 à 57,0172 ms.
- 45 tests préflight réussis ; espace disponible au démarrage :
  149187117056 octets, supérieur au minimum de 120 Gio.

## Décision méthodologique prise avant lancement

Le critère initial de 50 ms sur deux contrôles consécutifs n’a PAS été atteint.
Son remplacement par 100 ms maximum a été explicitement autorisé par l’utilisateur
et consigné avant toute collecte de production. Il ne s’agit pas d’une validation
rétroactive du seuil initial. Toutes les preuves du gate précédent sont conservées.

Décision datée : `C:\Users\Ramy\Documents\polymarket-crypto\analysis\d5\clock_sync_20260920_091052\gate_100ms_20260920_124639\METHODOLOGY_DECISION.json`.
Mesures de départ : `convergence_0001.json` et `convergence_0002.json` dans ce
même répertoire. La décision et l’état du gate au lancement sont joints dans
`PRELAUNCH_METHODOLOGY.json`.

Aucun timestamp historique ou prospectif source/réception n’est recalé ou corrigé.
Mesures NTP brutes conservées avant, pendant (toutes les heures) et après.

## Suite automatique

Le collecteur gère les rotations et reconnexions et s’arrête proprement après
la durée demandée. Après fermeture du writer uniquement : DATA QUALITY REPORT
puis deux replays NoTrade déterministes et comparaison des empreintes. Aucun
D5 Research, aucune optimisation ni aucun backtest pendant la collecte.
RESEARCH_ALLOWED reste false. Le suivi horaire ne relance pas la collecte.

Le PC doit rester allumé et alimenté. Réserve disque conservée par le superviseur ;
aucune suppression d’ancienne base pour libérer de l’espace.
