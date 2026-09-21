# Comparaison future Bonereaper / D5 — schéma seulement

Aucune lecture de SQLite D5 ni jointure effectuée. Aucun changement de RESEARCH_ALLOWED.

Cette étude couvre les marchés des 13–19 septembre 2026 UTC. Elle ne recouvre pas la collecte D5 actuellement active. Il faudra obtenir un nouvel intervalle public correspondant à la collecte terminée et validée ; ne pas substituer les carnets actuels à ceux des marchés historiques.

## Conditions préalables

1. Collecte terminée et close proprement.
2. DATA QUALITY REPORT et deux replays déterministes examinés et validés.
3. Autorisation de cette comparaison ; elle ne découle pas automatiquement du simple passage du rapport qualité.
4. Copie de travail ou connexion strictement en lecture seule après validation, selon le protocole alors autorisé.

## Clés et lignes

Une action est liée à un proxy vérifié, condition_id, token_id, durée et génération de marché. Ne jamais joindre uniquement sur Up/Down, slug partiel ou proximité temporelle. La clé de ligne publique est une signature documentaire, pas un identifiant garanti de fill.

Le schéma lisible par machine est `future_join_schema.json`. Les timestamps bruts restent intacts ; les colonnes en millisecondes sont des dérivés nommés, pas des corrections. `timestamp_raw_seconds` ne doit pas être renommé `decision_time`.

## Alignement sans regard vers le futur

Créer le bin temporel [T*1000, (T+1)*1000). Pour l'analyse conservatrice, retenir uniquement un carnet de la même identité/génération disponible strictement avant la borne inférieure. Vérifier aussi son timestamp source, son âge, l'expiration et les indicateurs de qualité. Le prix BTC et les caractéristiques sont calculés avec les observations disponibles avant cette même borne. Aucune interpolation utilisant le futur. Le calcul reste une description autour d'un timestamp API : un règlement tardif n'indique pas quand l'ordre a été décidé.

Pour l'inventaire préalable, utiliser l'état de la seconde précédente et conserver UNKNOWN après un événement non reconstructible. Ne pas utiliser l'ordre artificiel des fills de la seconde courante pour expliquer la décision. Ne pas transférer la position d'une rotation 5m au marché suivant.

## Questions à tester plus tard

- L'achat va-t-il vers le côté sous-pondéré ? Réduit-il le risque absolu ou normalisé ?
- Quel coût marginal observable aurait la paire, compte tenu du carnet et des frais vérifiés ?
- Les achats accompagnent-ils ou contrarient-ils une variation BTC antérieure ?
- Les achats 15m avant début correspondent-ils à une autre politique que les achats 5m ?
- Les conclusions tiennent-elles après exclusion des trous, marchés expirés, événements ambigus et timestamps de règlement tardifs ?

Inclure des contre-exemples et un modèle nul, tenir compte de la dépendance des observations par marché/jour et des comparaisons multiples. La référence de résolution (par exemple Chainlink TWAP selon la métadonnée du marché) et le flux BTC de D5 peuvent être différents. Sans flux privé ni heure de décision, « ce que voyait réellement le trader » demeure inconnu.
