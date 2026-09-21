# Quatrième smoke D5.1 — revue close

D51_DATA_QUALITY = PASS selon les critères figés. Le FAIL D5 historique reste définitivement inchangé. Ce smoke valide l’instrumentation, pas D6 ni la capacité de collecte longue.

Durée utile : 1320.013272 s ; 1 279 540 événements ; 6 marchés 5m et 2 marchés 15m ; 6 rotations ; 4 reprises réseau (8 marqueurs RECONNECT). Arrêt STOPPED, SQLite integrity_check OK, aucune violation FK, cross-market, post-expiry accepté, token manquant ou ancre ouverte. 1806 rejets dont 1292 OUT_OF_ORDER conservés. Horloge : 7 contrôles NTP PASS, offset absolu maximal 9.980 ms.

Revue complète : 2266.105 s (37 min 46 s). Résultats complets et états finaux des deux replays indépendants égaux ; SHA des résultats recalculés et vérifiés. Capital 500, zéro ordre/fill/inventaire.

SHA décisions : 35c20a26dd7b3b334b59a4f9bb19a529883cda9fa96700f686f1ba502bcf56bc
SHA résultats : 43d0d2d82a739daf81ee7590f9356912af9d51e6ad8e7e1029ba0a05be274845
SHA source : e3c1faa37b23d4f02225d0471efd4f5fe0a8095841a0d4f3ce31ad4aa3f0fc7f

## Diagnostic exhaustif après clôture

Lecture seule de tous les événements en 184.897 s ; source stat inchangée. Les seuils ci-dessous sont descriptifs, ne remplacent aucun critère qualité.

| Feed | Nombre | Médiane ms | p95 ms | p99 ms | Maximum ms | >5s |
|---|---:|---:|---:|---:|---:|---:|
| 15m | 415908 | 519 | 3832 | 6562 | 8180 | 2.310% |
| 5m | 841887 | 8740 | 49087 | 58937 | 61792 | 57.277% |
| BTC | 19854 | 466 | 1049 | 1689 | 3526 | 0.000% |

## Conséquence technique

Les gains sur le lot technique ne prouvent pas la capacité en production. Le smoke précédent avait une médiane 5m de 6087 ms, p95 29387 ms et 54.71% >5s. Les charges et fenêtres diffèrent : ni causalité de la dégradation ni gain de production ne sont démontrés. Pas de relance identique et pas de collecte longue avant correction ciblée.

Hypothèse à vérifier : traitement normalisation/sérialisation/SQLite synchrone limitant la vidange WebSocket. La capture publique sans normalisation était rapide mais non contemporaine ; ce n’est pas une preuve causale définitive. Le timestamp de disponibilité enregistré avant persistance ne mesure pas le coût complet du callback ni la file avant recv. Ajouter des mesures distinctes de temps CPU et mur de normalisation/callback/flush et de backlog réel sans retimer aucun événement. Étudier ensuite le stockage sans perte et le traitement des rafales avec équivalence complète.

Aucun D6 ni PAPER lancé. Les sources et tous les verdicts sont conservés.
