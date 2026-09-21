# Premier smoke D5.1 — FAIL préservé

Collecte prospective du 21 septembre 2026, environ 09:28–09:50 Paris. Durée utile 1 320,219 s (22 min). Ce smoke ne valide ni 24 h ni D6.

**D51_DATA_QUALITY = FAIL : W32TIME_SYNC_ERROR.** Le service a indiqué une erreur aux mesures vers 15 min, 20 min et après arrêt, malgré des sondes NTP indépendantes acceptables. Les preuves brutes restent conservées. Le verdict historique D5 demeure également FAIL, séparément.

| Contrôle | Résultat |
|---|---|
| Événements | 760 478, dont 745 392 BOOK et 13 541 BTC |
| Marchés distincts | 6 × 5m, 3 × 15m |
| Rotations | 7 : 5 × 5m, 2 × 15m |
| Reconnexions | 3 tentatives réseau, 3 fermetures d'ancres supplémentaires ; 6 marqueurs RECONNECT |
| Gaps >5 s | 0 sur les trois feeds |
| Gap maximal 5m / 15m / BTC | 1 618 / 1 514 / 3 438 ms |
| Cross-market / post-expiry accepté / missing tokens | 0 / 0 / 0 |
| Rejets | 1 461 : 1 007 hors ordre, 405 incomplets, 44 doublons, 5 expirés |
| SQLite integrity / foreign keys | ok / 0 violation |
| Ancres ouvertes | 0 |
| Arrêt | STOPPED ; COLLECTION_STOP=1, SESSION_END=3 |
| Supplément temporel v1 | 760 478 lignes, 1 490 784 côtés BOOK, aucun défaut signalé |
| Provenance | Code inchangé pendant collecte ; code archivé après revue |
| Replays 1 et 2 | Complets ; décisions, résultats et états finaux égaux |
| NoTrade | Capital 500, zéro ordre/fill/inventaire |

Chaque replay : décisions SHA-256 `046225ccc1d6f4d5e93e2f60d605069805406f01c1bdf267da6e034b69667b12` ; résultats SHA-256 `59812d88afeff2c65b169e366268476200e122a86dc2f18f629d628eef75ac3c`.

Source SHA-256 `596f2a14f3ce2bde7623943d6f2046d101dd758de0af4309a176d4cac74a15fb`. Stat source inchangé. Revue principale : 1 178,085 s (~19 min 38 s), plus calcul final de l'empreinte source.

## Limites et suite prospective

Le supplément v1 n'avait pas de contrôle explicite d'égalité wire_event_ts_ms / source_metadata ; un test synthétique a démontré ce manque après la revue. Il a été ajouté, avec contrôles de fermeture supplémentaires et distinction des marqueurs de reconnexion. Ces additions ne requalifient pas le premier smoke. Le code original est archivé dans code_at_review et la vérification indépendante dans INDEPENDENT_COMPLETION_CHECK.json.

La première correction prospective du polling W32Time (64–512 s) a échoué au dernier contrôle prolongé. L'essai suivant fixe le polling à 64 s et exige vingt minutes d'observation sans échec avant toute nouvelle collecte. Aucun seuil qualité n'est relâché, aucune donnée passée corrigée. Nouvelle collecte seulement après observation réussie, tests et double préflight frais.
