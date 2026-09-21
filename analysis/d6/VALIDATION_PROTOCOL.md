# D6 — protocole de validation préparé

Aucune validation économique. Tests uniquement synthétiques, sans réseau, SQLite ou données Bonereaper/D5. Aucun changement de RESEARCH_ALLOWED.

## Gate réel futur

Writer fermé, hash/manifeste vérifié, rapport qualité accepté, deux replays concordants, recherche explicitement autorisée. Tout manque bloque. Un hash replay seul ne valide pas le dataset. Les fixtures true/false des tests sont fictives : le futur runner devra vérifier les preuves, pas croire un JSON déclaratif.

## Partitions temporelles par MARKET_SLUG

Proposition préenregistrée : 12 premières heures TRAIN, 6 suivantes VALIDATION, 6 dernières OOS à partir du début réel. La marge de collecte n'autorise pas à déplacer les bornes selon résultats. Si couverture insuffisante, réviser AVANT ouverture des labels ou demander nouvelle collecte ; ne pas raccourcir OOS discrètement.

Une condition ET un slug dans une seule partition ; tous ses tokens/legs/targets ensemble. Pas de shuffle de fills. Vérifier intervalles feature_start → label_available_end (incluant inventaire préalable, lookback et règlement). Purger les marchés traversant une frontière au lieu de les découper. Embargo proposé 60 s, augmenté si horizons/latences l'exigent avant examen des résultats. Les 5m/15m contemporains restent dépendants même avec slugs différents.

Manifeste slug→split et raisons de purge figés/hashés. TRAIN : transformations et apprentissage ; VALIDATION : sélectionner parmi essais enregistrés. OOS ouvert UNE fois après gel code/paramètres/features/exécution/manifestes. Journal d'accès persistant atomique dans le futur runner ; le test présent ne le démontre qu'en mémoire. Toute retouche après résultat OOS nécessite nouvel OOS indépendant.

Une journée ne fournit pas une validation inter-régimes. Bootstrap/permutation par marché et blocs temporels, effectif utile explicite ; ne pas considérer tous les fills comme indépendants. H1–H8 : correction des familles et registre complet des variantes/seeds.

## Tests synthétiques

Depuis analysis/d6 : `python -B -m unittest discover -s tests -p "test_*.py" -v`.

Contrats testés : filtres source/réception/disponibilité de chaque côté ; égalité ambiguë ; as-of backward et lags ; identités/token/slug/durée/session/génération ; début de génération ; expiration ; fraîcheur d'un seul côté ; temps manquant/gap ; ordre des entrées et ties ; invariance à l'ajout du futur ; inventaire même seconde ; features interdites ; gate ; partitions/embargo ; OOS unique ; formules et consommation d'un budget de profondeur synthétique.

Ne valide pas un adaptateur SQLite, décompression réelle, moteur de replay complet ou queue réelle. Tests d'intégration futurs sur fixtures séparées après implémentation, jamais base active.

## Challenge d'un résultat très rentable

Ne pas rejeter automatiquement. Conserver le résultat UNVERIFIED tant que les points suivants ne passent pas :

| Risque | Vérification |
|---|---|
| Lookahead/future time | Provenance de chaque valeur, retrait du futur, trois horloges, aucun règlement dans X |
| Cross-market contamination | Toutes les clés, génération, tokens, partitions et bornes |
| Double liquidité | Consommation persistante entre snapshots/reconnects et ordres concurrents |
| Capital reuse | Cash/réserves globaux, débit à chaque fill, règlement non anticipé |
| Fees/slippage | Barèmes/arrondis sourcés, stress annoncés, gross/net distincts |
| Settlement | Oracle correct, pas paiement à simple expiry ou double paiement |
| Risque caché | Legs résiduels conservés, valorisation prudente, exposition maximale |
| Concentration | Contributions des meilleurs marchés et diagnostic annoncé sans eux |
| Dépendance | Blocs temps/marchés, chevauchement 5m/15m, effectif réel |
| Incertitude temporelle | Sémantique API, NTP, segments douteux et sensibilités sans recalage |
| Tests multiples | Tous essais/seeds comptés ; aucun ajustement après OOS |

Reproductibilité future : mêmes données/seed/config => hashes identiques décisions/fills/ledger/métriques. Les deux replays NoTrade de D5 ne valident pas le futur moteur D6. Aucune conclusion de rentabilité ici.

## Résultat de préparation — 20 septembre 2026

Commande exécutée depuis le dépôt : `python -B -m unittest discover -s analysis/d6/tests -p "test_*.py" -v`.
Résultat : **35 tests réussis**, avec sous-cas couvrant les trois horloges et chaque côté. Aucun accès réseau/SQLite, aucune recherche réelle ni conclusion de rentabilité. Le contrat DepthBudget est une fixture d'épisode de liquidité fixe ; le renouvellement entre snapshots, la queue et les règlements complets restent à implémenter et à tester ultérieurement.
