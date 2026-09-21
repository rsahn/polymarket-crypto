# D6 — pipeline analytique terminé

Statut : COMPLETE. Ce statut concerne la conversion, pas le PASS qualité D5 ni une stratégie rentable.

- Temps total depuis le lancement initial, incidents et reprises inclus : 49.90 minutes.
- Source SQLite conservée : 26,186,612,736 octets.
- Parquet final (tables + BTC + features) : 844,931,462 octets.
- Source inchangée (taille/mtime vérifiés) : True.
- SHA-256 source : `e4f7212036818141c86e2d45c0082adaa834126f61db3060c3809264c588d0bd`.
- Événements : 7,518,713.
- Côtés de carnet : 14,882,424.
- BOOK / features : 7,441,212 / 7,441,212.
- Marchés distincts : 38×5m,13×15m.
- Enveloppes post-échéance détectées par le contrôle essentiel : 0.
- Construction finale des features : 182.26 secondes.
- Maximum mémoire observé du processus de finalisation : 668.5 Mio (inclut les allocations hors budget interne DuckDB384MB).

## Incidents conservés

1. Export initial interrompu par partage Windows de progress.json. Préfixe Parquet4,940,000 événements vérifié et réutilisé dans un nouveau dossier ; aucune correction de données.
2. Jointure globale finale dépassant384MB internes à DuckDB. Source déjà exportée et SHA enregistré. Reprise uniquement sur Parquet par plages de100,000 event_id,1thread ; équivalence sur fixture vérifiée. Finalisation en3min06 sans réouverture SQLite.

Toutes les anciennes sorties et bases sont conservées. Les845Mo sont le jeu analytique final, pas l'espace total occupé par les essais/copies. Aucune suppression ni compression de la DB historique.

## Provenance et limites

Les JSON BOOK redondants sont omis dans le dérivé ; les enveloppes, identités, générations, tokens, timestamps bruts et profondeur structurelle des deux côtés sont conservés. La base brute complète reste disponible. Aucun recalage temporel. available_ts_ms n'est pas un timestamp monotone matériel.

Les décomptes exportés concordent, mais integrity_check, clés étrangères, contrôles complets D5 et deux replays historiques restent du ressort de l'audit PID12408. Ne pas assimiler le contrôle essentiel post-expiry à toute la revue qualité.
