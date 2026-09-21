# Auditeur D5 suivant — candidat séparé

Version préparée pour les prochaines collectes. Ne remplace pas l’audit PID 12408. Aucun fichier backend/app ni base D5 de production modifié. Aucun audit supplémentaire de la collecte réelle lancé.

## Optimisations

- Fusion des contrôles identité BOOK, post-expiration de l’enveloppe et token manquant : trois parcours deviennent un parcours. Les contrôles sides/anchors/hedges restent distincts et conservés.
- Gaps par marché : parcours ordonné par event_id, état borné par nombre de marchés ; suppression du tri global pour la fenêtre SQL et du GROUP BY associé. Sémantique des timestamps régressifs et des groupes à un seul événement conservée, y compris NULL.
- Connexion mode=ro + query_only ; fermeture garantie même sur erreur.
- Début/fin de chaque requête, SQL explicite, durée écoulée, heartbeat SQLite environ toutes les deux secondes de travail VM. Le heartbeat ne peut garantir une périodicité pendant une attente I/O.
- Lignes/total/pourcentage réels pour le parcours des gaps, tous les 100 000 BOOK. Pour les agrégats SQL, pourcentage inconnu ; instructions VM indicatives, jamais assimilées à des lignes validées. Aucune ETA fictive.

## Validation effectuée

8 tests réussis : schémas 1/2, compression, données saines et corrompues, trous/régressions temporelles, base vide, singleton, session absente/fermeture. Comparaison intégrale des rapports avec l’auditeur de référence ; SHA-256 des bases synthétiques inchangé avant/après audit.

Benchmark synthétique 10 000 événements, ordre référence/candidat/candidat/référence : référence ~0,185 s, candidat ~0,161 s, soit environ 13 % de temps en moins sur cet échantillon. Résultats complets et empreintes identiques. Ce petit essai en cache ne prédit pas le gain sur 26 Go ou un autre disque. Voir BENCHMARK.json.

## Avant toute prochaine grosse collecte

Le candidat doit être intégré et validé avec la chaîne complète quality.py (integrity_check, foreign keys, deux replays) après clôture de la revue actuelle, avec provenance distincte. Le candidat ne supprime ni ne remplace ces contrôles. Il ne valide pas à lui seul le dataset. Ne pas le basculer dans le processus actif.

Restent à mesurer avant une utilisation à grande échelle : performance sur une fixture volumineuse représentative, coût des autres jointures/tris et integrity_check, mémoire, espace temporaire et surcoût de télémétrie. Aucun facteur d’accélération de production garanti. Les prochaines améliorations pourront fusionner davantage d’agrégats après tests d’équivalence ; aucune création d’index ni modification de la base historique.

Tests (depuis le dépôt) :

```powershell
backend\.venv\Scripts\python.exe -B -m unittest discover -s analysis\d5\auditor_next -p test_audit_next.py -v
```

CLI disponible pour futures fixtures/bases closes autorisées : audit_next.py --db CHEMIN --session SESSION --out NOUVEAU_RAPPORT. Événements de progression JSON sur stderr. Ne pas exécuter maintenant sur la collecte D5 en cours de revue.
