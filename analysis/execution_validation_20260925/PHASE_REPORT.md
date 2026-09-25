# Exécution BTC D6 — phase de correction hors ligne

Verdict : OFFLINE_PHASE_VALIDATED_NOT_READY_FOR_LIVE.
Aucun raccordement du transport monétaire au runner. BTC V1 et la logique du signal inchangés.
Les deux interrupteurs REAL_ORDERS_ENABLED et LIVE_EXECUTION_ARMED sont explicitement false dans .env (ignoré par Git).

## Commits fonctionnels
- 11c829d : parsing strict, comptabilité des quantités, unités USDC, recovery fermé et régressions.
- 80263ac : test writer aligné sur le contrat volontaire du commit 12f3e822 (65536 éléments, 256 Mio, lots 256). Aucun changement du writer.
- 0e5a94c : rejet des identifiants ACK contradictoires.
- f5565e9 : contrôleur persistant, lecteurs explicites et scénarios de panne.
- 00e6b49 : verrou one-shot, audit élargi et harnais sans accès monétaire.

## Tests et méthode
35 cas pytest ajoutés : 13 régressions parsing/recovery/solde, 19 contrôleur, 3 sources.
Certains correctifs avaient été appliqués avant la demande test-first : leurs 12 régressions ont été exécutées sur une copie isolée du commit audité 4cb928c, donnant 12 échecs (REGRESSION_RED.log), puis 33 réussites avec les tests lifecycle existants (REGRESSION_GREEN.log).
ACK contradictoire : 1 échec avant correction (ACK_RED.log).
Raccordement ExecutionInvariantGuard : 1 échec avant raccordement (CONTROLLER_RED.log), puis 19 réussites.
Lecteurs de sources : 3 échecs avant création (SOURCES_RED.log), puis 22 réussites avec le contrôleur (SOURCES_GREEN.log).

Backend : 176 passed, 0 failed, 8 sous-tests réussis.
Suite élargie backend + tests historiques + audit D5 + review D5.1 + D6 préparation/pipeline/recherche/paper_runtime + C3/D4 : 293 passed, 0 failed, 25 sous-tests réussis, 1 erreur de collecte.
Cette erreur préexistante concerne tests/test_btc_collector_phase_a.py : backend.collectors et backend.storage n'existent plus dans ce dépôt. Test conservé, aucun skip ajouté. Trois avertissements DuckDB de dépréciation sont également présents.
Commandes et sorties : ALL_PROJECT_PYTEST.log et STATIC_AUDIT_FINAL.log. Le code de sortie global pytest reste non nul à cause de l'erreur de collecte ; ne pas annoncer toute la suite verte.

## Diff des invariants
| Avant | Après |
|---|---|
| SDK dict converti en texte | dict conservé |
| Statut inconnu pouvant devenir FILLED | statuts limités, valeurs finies et champs cohérents requis |
| Sortie projetée sur filled_shares | projection explicite entry/exit ; sortie met sold_shares à jour |
| Local CLOSED autorisant une entrée | réconciliation distante obligatoire |
| Solde brut comparé à 25 | solde et allowance convertis en USDC avant comparaison |
| ACK ambigu sans protocole persistant | intention persistée avant appel ; ambiguïté bloque sans deuxième soumission |
| Cancel ACK assimilable à fin du reliquat | lecture terminale après annulation ; fill tardif pris en compte avant sortie |
| Sortie demandée sans contrôle final global | quantité confirmée seulement ; CLOSED après sold=bought et preuve de compte flat |
| États optimistes constants du staging | lecteurs explicites ; absence de source => refus |
| Écriture locale seule | contrôleur : état et événements dans une même transaction SQLite synchronous=FULL |
| One-shot pouvant acheter puis s'arrêter | --execute refusé avant chargement des identifiants ; transport hard-locked |

## Preuve d'absence de soumission
Le harnais intercepte 16 méthodes SDK (envoi, annulation et création/signature) et interdit les connexions externes. Résultat : 0 tentative SDK monétaire, 0 connexion externe tentée. Trois appels au transport de production sont des tests du verrou USER_APPROVAL_REQUIRED avec un client sentinelle qui échoue au moindre accès SDK. Les cycles de fills utilisent uniquement un transport factice.
Audit AST : 79 fichiers ; appels SDK monétaires confinés au transport ; ses trois méthodes commencent par un refus inconditionnel. Le contrôleur délègue seulement à son transport injecté et n'est pas raccordé au runner.

## Problèmes encore ouverts avant live
- Ancien test phase A non collectable : migration ou restauration de son contrat à traiter séparément.
- Les lecteurs book/risk/geo/signal/position sont explicites et testés, mais les adaptateurs authentifiés de compte complet et les abonnements de production ne sont pas encore raccordés. Sans ces sources, staging refuse. Aucun état réel n'a été inventé et aucun solde/wallet n'a été revalidé pendant cette phase.
- Le SDK observé ne suffit pas encore à démontrer une vue complète des ordres ouverts et de l'inventaire : la capacité distante doit être établie avant live.
- Après un crash avec un ordre ambigu ou un cycle non CLOSED, politique actuelle : RECOVERY_REQUIRED, aucune resoumission/reprise automatique. Une procédure de résolution distante explicite reste nécessaire.
- Contrôleur expérimental : pas de runner monétaire, pas de validation réseau réelle, pas de métriques de fills/frais/PnL réels. Prix de sortie fourni par l'appelant ; politique de sortie/latence complète à raccorder ultérieurement.
- La transaction SQLite protège son propre journal ; elle ne rend pas atomique une écriture distante CLOB. L'incertitude entre envoi et ACK reste bloquante par conception.
- Les tests démontrent les contrats locaux, pas la rentabilité de V1 ni son admissibilité statistique.

Cette phase ne constitue pas une demande de feu vert pour envoyer un ordre réel.
