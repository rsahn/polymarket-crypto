# Évaluation de bascule D5 — 20 septembre 2026

## Verdict

Équivalence fonctionnelle : les contrôles historiques sont conservés par auditor_next appelé en remplacement de audit() dans la fonction review() inchangée de quality.py. 15 tests réussis, dont 6 comparaisons de chaîne complète et une matrice des seuils. Aucun déploiement de cette substitution dans le processus actif.

Bascule propre immédiate : NON DISPONIBLE. Le PID 12408 est sans console attachable : probe AttachConsole retourne erreur Windows 6. Le probe utilise send=False, aucun signal envoyé. Le contrôleur appelle FreeConsole après le signal autrefois adressé au collecteur. Il ne propose aucun fichier d’annulation, canal IPC ni gestionnaire coopératif d’arrêt SQLite. Pas de checkpoint de reprise d’audit. Un Stop-Process/taskkill serait une terminaison forcée, pas une fermeture propre démontrée. Aucun de ces ordres n’a été exécuté.

Laisser le processus terminer est actuellement la seule procédure propre établie. Ne pas prétendre qu’une absence de console autorise une injection, un kill ou une modification du processus. Aucun gain global de temps garanti : la nouvelle version a gagné environ 13 % sur une petite fixture, mais recommencer abandonnerait tout travail non publié.

## Comparaison exhaustive des contrôles existants

| Contrôle / données du rapport historique | Chaîne candidate | Équivalence |
|---|---|---|
| Schémas 1/2, session explicite ou latest, existence session | audit_next | Même validation et sélection |
| SESSION, configuration, version, statut brut | audit_next | Même ligne, FAILED jamais transformé |
| KINDS, TOTAL_EVENTS, ROWS BOOK, BTC_TICKS, RECONNECTS | audit_next | Même agrégation |
| MARKETS : durée, slug, condition, tokens, snapshots, premier/dernier receive, durée, générations | audit_next | Même SQL |
| REAL_MARKETS, 5M_MARKETS, 15M_MARKETS | audit_next | Même calcul |
| Identité BOOK contre markets (condition/slug/tokens/durée) | audit_next | Prédicat identique, fusion dans agrégat |
| Identité book_sides UP/DOWN contre événement | audit_next | Même SQL |
| Identité anchors contre événement | audit_next | Même SQL |
| Identité hedge ACCEPT contre anchor et token opposé | audit_next | Même SQL |
| CROSS_MARKET_VIOLATIONS | audit_next | Même somme des quatre contrôles |
| POST_EXPIRY_EVENTS : source/réception/disponibilité enveloppe | audit_next | Prédicat identique, fusion dans agrégat |
| POST_EXPIRY_ANCHORS | audit_next | Même SQL |
| POST_EXPIRY_BOOK_SIDES : source et réception | audit_next | Même SQL |
| INCOMPLETE_BOOK_EVENTS : exactement deux côtés | audit_next | Même SQL |
| MISSING_TOKEN_IDS : NULL ou chaîne vide | audit_next | Prédicat identique, fusion dans agrégat |
| LATENCY BOOK/BTC : n, moyenne/min/max, source absente, avance >2s, processing moyen/max | audit_next | Même SQL |
| GAPS par slug : max, nombre >5s, somme des gaps >5s | audit_next | Parcours event_id et état par slug ; mêmes valeurs, y compris singleton NULL et régressions |
| DEPTH par côté : n, bid/ask moyen/min/max, zéros, classes de profondeur, spread | audit_next | Même SQL |
| REJECTIONS par reason (décompression schémas 1/2) | audit_next | Même SQL/UDF |
| BOUNDS disponibles min/max | audit_next | Même SQL |
| AVAILABILITY_REGRESSIONS globales ordonnées par event_id | audit_next | Même SQL |
| EXPIRED_OPEN_ANCHORS | audit_next | Même SQL |
| SMOKE_FAILURES / SMOKE_VALIDATED : intégrité, feeds, rotations, générations, horloge source >2s | audit_next | Même logique |
| SQLITE_INTEGRITY_CHECK complet | quality.review original | PRAGMA integrity_check inchangé, pas quick_check |
| FOREIGN_KEY_VIOLATIONS | quality.review original | PRAGMA foreign_key_check inchangé |
| OPEN_ANCHORS, toutes ancres résiduelles ouvertes | quality.review original | Même SQL |
| SESSION_END, durée acquisition, durée session, durée murale, COLLECTION_STOP_TS_MS | quality.review original | Mêmes données et calculs |
| POST_EXPIRY_ACCEPTED union enveloppe/côtés | quality.review original | Même SQL complet |
| ROTATIONS_BY_DURATION / ROTATIONS | quality.review original | Même transitions ACTIVATE par durée |
| RECONNECTIONS Polymarket/Binance | quality.review original | Mêmes compteurs |
| REJECTED_EVENTS / OUT_OF_ORDER_REJECTED | quality.review original | Même somme et motif |
| FEED_GAPS 5m/15m/BTC : événements, bornes, couverture, max/somme/nombre, exemples, régressions receive, gaps initiaux/finaux | quality.review original | Même parcours couvrant frontières et rotations |
| CODE_CHANGED_DURING_COLLECTION | quality.review original | Même comparaison de provenance ; fournir final_code_version, ne pas l’omettre |
| Deux replays NoTrade séparés | quality.review original + replay_database original | Deux nouvelles instances, même session, capital500 |
| Nombre de décisions/événements et complétude vs TOTAL_EVENTS | quality.review original | Même comptage sink et comparaison |
| SHA-256 décisions / SHA-256 résultats / égalité des résultats complets et état final | quality.review original | Même encodage canonique et comparaisons |
| Zéro ordre/fill, cash500, paired/directional inventories nuls | quality.review original | Même contrôle inert |
| quality_gate / QUALITY_FAILURES | fonction originale réutilisée | Aucun seuil modifié : durée10800 pour décision 3h, couverture chaque feed, gaps >5s, bornes >10s, régressions, code, statut, intégrité, anchors et replays |
| RESEARCH_ALLOWED | chaîne originale | Reste false |

Les groupes de requêtes fusionnées ne multiplient pas les lignes : markets a une clé unique condition_id/market_slug. Les CASE conservent la logique SQL NULL des WHERE d’origine. Aucun changement de priorité, filtre de session ou seuil. Le tri externe des gaps devient mémoire proportionnelle au nombre de slugs, sans suppression de lignes.

## Preuves et limites

Commande exécutée depuis C:\Users\Ramy\Documents\polymarket-crypto :

```powershell
backend\.venv\Scripts\python.exe -B -m unittest discover -s analysis\d5\auditor_next -p 'test_*.py' -v
```

Résultat : 15 tests PASS. Les nouveaux tests exécutent la fonction review() originale dans deux espaces de variables indépendants, avec seulement la fonction audit substituée dans la copie. Aucun monkeypatch du module actif, aucune modification backend/app. Comparaison des rapports JSON complets, des deux REPLAY_n.json et SHA-256 du fichier de fixture avant/après. Cas de chaîne : schémas 1/2, FAILED volontaire, ancres ouvertes, violation FK, post-expiration des côtés ; matrice de seuils et replay divergent refusé. Une première fixture FK créait involontairement une collision de clé primaire ; fixture corrigée en conservant des IDs orphelins distincts, puis suite entière repassée.

Les tests ne constituent pas un audit de la DB réelle. Aucun second audit réel lancé. Les limites de l’ancien auditeur restent les mêmes : par exemple la régression source par token n’est pas contrôlée explicitement comme la disponibilité et la réception. Le contexte d’arrêt COLLECTION_STOP et l’évolution NTP doivent encore être rapprochés du verdict final. Ne pas confondre conservation de tous les contrôles historiques et satisfaction automatique du protocole utilisateur élargi.

## Procédure de décision

1. Attendre le verdict du PID 12408, qui n’a reçu aucun signal.
2. Conserver rapports, journaux et statut brut. Ne pas redémarrer la collecte.
3. Si une nouvelle revue est ensuite nécessaire et autorisée : utiliser un nouveau répertoire, même session/DB en mode lecture seule, même minimum10800 et même contrôle de provenance ; injecter seulement l’auditeur candidat dans une instance séparée de review, préserver integrity/FK/double replay et critères de rejet.
4. Un runner de production doit encore être matérialisé/validé ; les tests de substitution ne sont pas une commande de bascule opérationnelle. Ne pas lancer audit_next seul en croyant exécuter toute la chaîne.

Aucune commande d’interruption propre du PID actuel n’est fournie car aucune n’a été démontrée. Toute terminaison forcée nécessiterait une autorisation explicite distincte et devrait être qualifiée comme telle, avec préservation des preuves et reprise intégrale ; elle n’est pas proposée comme solution propre.
