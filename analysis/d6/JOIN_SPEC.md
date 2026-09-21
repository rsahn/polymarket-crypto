# D6 — jointure future, non exécutée

Aucune ouverture SQLite. Contrat synthétique dans tests/, pas d'adaptateur de production.

## Clés fortes

Action : proxy vérifié, condition_id, token_id, market_slug, market_duration, outcome, side, prix/quantité API, usdcSize, hash transaction et référence brute. Un hash transaction n'est pas un fill ID unique. Source canonique activity ; trades sert au contrôle, pas à ajouter les mêmes opérations deux fois.

D5 : mêmes condition/slug/durée/token, session_id et génération active. Le token doit correspondre à l'outcome. La génération se déduit des événements d'activation/invalidation disponibles AVANT la borne, jamais de la seule action publique. Intervalles demi-ouverts ; ambiguïté => exclusion. Reconnexion ne permet pas de revenir à l'ancienne génération. BTC garde son identité de feed/session, sans condition Polymarket fictive.

## Schéma D5 vérifié par lecture statique du code uniquement

Sources : backend/app/d5/schema_v2.sql, store.py, live.py, features.py.

| Information | Champ et restriction |
|---|---|
| Source | events.event_ts_ms ET book_sides.event_ts_ms pour chacun des deux côtés |
| Réception | events.received_ts_ms ET book_sides.received_ts_ms |
| Disponibilité | events.available_ts_ms : max de l'heure murale d'insertion/argument, réception et valeur précédente |
| Ordre déterministe | session_id + event_id ; pas ordre d'exchange prouvé |
| Monotone natif | CLOCK_SAMPLE.monotonic_ns périodique, environ toutes les 30 s ; pas par BOOK/BTC |
| Profondeur | book_sides.bids_json/asks_json ; schéma 2 JSON texte ou BLOB zlib réversible |
| Identité/échéance | markets, events.generation, tokens des deux book_sides |

IMPORTANT : available_ts_ms est non décroissant mais n'est PAS une mesure monotonic_ns matérielle. Ne pas inventer des timestamps monotones par événement à partir des échantillons. NTP et CLOCK_SAMPLE caractérisent l'incertitude et les discontinuités ; aucun recalage des timestamps historiques. Segment temporel douteux => exclusion ou statut non identifiable.

## Borne causale

Conserver T_api_s brut ; colonnes dérivées bin=[1000*T,1000*(T+1)). Ce bin décrit la résolution API, pas un intervalle certifié de décision/exécution. Budget d'incertitude externe défendable => B=début_bin-budget. Budget fixé par qualité temporelle, jamais par performance. Semantique/retard API non borné => refuser la prétention « avant décision » ; une analyse contextuelle séparée ne devient pas causale par un simple décalage.

Par défaut strictement avant B pour source, réception ET disponibilité, enveloppe ET chaque côté. Cela satisfait <=T en excluant les égalités ambiguës. Inclusion de l'égalité uniquement avec ordre causal prouvé, absent pour les secondes API.

## As-of backward et lags

1. Filtrer toutes les clés et le segment/génération active. Exclure gaps, rejets, invalidation, source manquante/future et réception/disponibilité future.
2. Exiger début_génération <= disponibilité et B < échéance. Ne pas transférer de snapshot entre rotations.
3. Fraîcheur primaire proposée : âge maximum 1000 ms pour TOUS les temps des deux côtés et de l'enveloppe. Sensibilité à geler avant résultats. Un côté périmé invalide la paire.
4. Retenir le dernier (available_ts_ms,event_id) admissible ; jamais nearest-neighbor bidirectionnel. Entrées non triées ne doivent pas changer le résultat.
5. Pour chaque lag h, recommencer à B-h avec les mêmes filtres et sa propre fraîcheur. Une donnée reçue tardivement ne répare pas le passé.
6. BTC : source/réception/disponibilité admissibles, feed et segment cohérents ; aucun retour à travers un gap/reconnect non couvert.
7. Inventaire préalable : opérations de la même condition strictement AVANT la seconde cible. Fill cible et autres fills de cette seconde exclus ; inventaire initial inconnu ou brûlages non reconstruits => UNKNOWN, pas zéro.

## Sorties et fenêtre

Chaque ligne future conserve clés, B, event IDs, temps bruts, âge, budget temporel, quality flags connus à B, inventory_confidence, provenance, versions et split. Targets et résolution dans une table distincte. Ne pas transformer un rejet futur en feature du passé.

Intervalle exact issu du rapport final D5 ; extraction API élargie uniquement pour récupérer les bins de frontière, séparés ensuite en intérieur certain/frontière ambiguë/extérieur. Bootstrap d'inventaire distinct. La semaine Bonereaper historique ne peut être jointe aux carnets d'une autre semaine.

Futur chargeur : fichier fermé validé, hash vérifié, URI SQLite read-only, décodage réversible sans réécriture, aucune lecture active aujourd'hui. Le contrat synthétique ne vérifie ni ce chargeur ni l'exhaustivité réelle.

## Précision sur la représentation des tests

Les fixtures représentent chaque côté par source/receive/available pour tester les contraintes. Dans le schéma D5 réel, book_sides n'a pas de colonne available propre : l'adaptateur futur devra lui appliquer la disponibilité de l'événement parent, sans inventer une heure individuelle de traitement. Cette projection conservatrice ne fournit pas une horloge monotone matérielle.
