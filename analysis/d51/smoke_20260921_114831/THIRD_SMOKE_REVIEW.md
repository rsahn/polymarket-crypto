# Troisième smoke D5.1 — revue terminée

Le 21 septembre 2026, la revue complète du smoke 114831 est PASS selon le protocole figé avant lancement. Le D5 historique, le smoke092802 et le smoke104534 gardent leurs verdicts FAIL.

- Collecte utile: 1320.0072473 s; SHADOW/NO_TRADE500; STOPPED.
- 1 366 126 événements: 1 329 698 BOOK, 34 376 BTC. Six marchés5m et deux15m; six rotations (5+1).
- Cinq tentatives de reconnexion réseau, dix marqueurs RECONNECT. Aucun gap de réception >5s; maximum5m2940ms,15m2818ms,BTC2054ms.
- 1963 rejets, dont1568 OUT_OF_ORDER,283 INCOMPLETE_BOOK,109 DUPLICATE_EVENT et3 POST_EXPIRY_REJECT.
- Cross-market/post-expiry acceptés/tokens manquants/ancres ouvertes/régressions réception ou disponibilité: zéro. Supplément temporel sans défaut;1 COLLECTION_STOP et3 SESSION_END. Les227 régressions du timestamp brut du dernier message (maximum286ms) restent conservées, diagnostiques; le contrat composite D5.1 est vérifié.
- SQLite integrity_check OK, foreign_key_check aucune violation, provenance conforme, sept séries NTP PASS.
- Deux replays indépendants de1366126événements, résultats complets égaux et empreintes de résultats recalculées indépendamment. Capital500, zéro ordre/fill/inventaire.
- Décisions SHA256: 422e893ebbcef9144a3c82ebb58ab8611918953285a9e4d6e44a1db34b903120
- Résultats SHA256: f029be0b486dfacc53c4c44a383b32a851b1043204916737445bf4b2928f9b9b
- Source SHA256: 5b7e37193224e930302f6d9063dcabef597c44ad2b0c4e4869a90abab7d46ee4; stat inchangé.
- Revue close vers12h45:33Paris; PID10560 terminé; keep_awake=false.

## Diagnostic complémentaire de réception

Après fermeture de la revue, post_review_latency/LATENCY_DIAGNOSIS.json recense tous les événements en lecture seule (193.13s), source inchangée. Ce diagnostic ne remplace aucun verdict ni seuil.

| Flux | Médiane wire-age | p95 | Maximum | Part >5s |
|---|---:|---:|---:|---:|
|5m|6087ms|29387ms|37857ms|54.7115%|
|15m|468ms|2416ms|8127ms|0.8264%|
|BTC|455ms|997ms|3794ms|0%|

wire-age = réception moins timestamp du message source; aucune correction d'horloge appliquée. Les âges source composite et wire sont presque égaux. Le délai disponibilité-réception mesuré (p99=1ms) n'inclut pas nécessairement la persistance effectuée après fixation de disponibilité, ni l'attente antérieure dans les files réseau/WebSocket. Il ne prouve pas que le traitement local est assez rapide. NTP offset maximal13.52ms ne suffit pas à expliquer des secondes de retard.

Prochaine action: localiser le goulet par inspection/profilage borné, puis si nécessaire observation publique indépendante de réception, sans ordres. Ne pas relancer à code inchangé pour chercher un meilleur PASS. Ne pas provoquer une reconnexion pour jeter une file. Optimisations uniquement avec preuve de conservation/équivalence. Aucune collecte longue ou recherche D6 lancée à ce stade; aucun PAPER. Le smoke ne constitue pas une validation statistique D6.
