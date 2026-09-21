# Cinquieme smoke D5.1 — revue complete

D51_DATA_QUALITY = PASS pour instrumentation uniquement. D5 historique reste FAIL. Aucune validation statistique D6 et aucun PAPER.

Collecte utile 1320.005 s, 1 400 618 evenements, 1 371 683 BOOK, 26 956 BTC ; six marches 5m et deux 15m ; six rotations et trois reconnexions naturelles. Arret STOPPED, un COLLECTION_STOP, trois SESSION_END. Capital 500 ; zero ordre, fill et inventaire.

Revue 8/8 PASS en 2291.145 s. SQLite integrity_check OK, foreign_key_check sans violation, cross-market/post-expiry/missing tokens/ancres ouvertes/regressions acceptees sans defaut. Provenance et source inchangees. Sept preuves NTP PASS, offset absolu maximal 21.569371 ms. Rejets preserves : 1246 hors ordre, 511 incomplets, 136 doublons, cinq post-expiration. Les 193 regressions de timestamps wire bruts restent diagnostiques ; aucune correction appliquee.

Comparaison independante des resultats complets et hashes recalcules PASS. Decisions SHA-256 : 1e1b559a6d586d717a4f3034b495c2574f6edc34fc27f0c44242f85b2f41677c. Resultats des deux replays : 9c98f4bf1f8db560b3dd63545855db725639b4489aa558d520409e5e7297fa54.

## Retard source / reception — diagnostic exhaustif

| Feed | Evenements | Mediane ms | p95 ms | p99 ms | Max ms | >5 s |
|---|---:|---:|---:|---:|---:|---:|
| 5m | 932345 | 1255 | 26094 | 31376 | 33351 | 33.346% |
| 15m | 439338 | 314 | 1208 | 2426 | 3864 | 0.000% |
| BTC | 26956 | 316 | 716 | 1124 | 2419 | 0.000% |

Diagnostic readonly 1400618 evenements en 204.037 s ; stat source inchange. Les valeurs de processing avant persistance ne mesurent pas tout le cout du callback.

## Decision technique

La baisse descriptive du retard par rapport au smoke precedent ne prouve pas un gain causal : charges et reseau differents. Le retard 5m persiste, donc pas de longue collecte inchangee ni de recherche D6 immediate. Prochaine cible : cout CPU de normalisation/serialisation/persistance, avec benchmark technique sur captures conservees et equivalence exhaustive avant toute nouvelle experience. Aucun seuil qualite modifie. Les compteurs stage_timing dans status.json sont le dernier echantillon, pas les totaux finaux.
