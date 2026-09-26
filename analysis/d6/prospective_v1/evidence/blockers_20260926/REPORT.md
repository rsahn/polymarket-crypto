# BTC V1 PROSPECTIVE — résolution des seuls blockers démontrés

**BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED**

Le travail apporte une révision candidate d'observabilité testée, une preuve plus précise sur les frais, une réduction lossless mesurée ×14.28 et un diagnostic quantifié du replay. Aucun des trois gates réels n'est artificiellement passé à READY. Aucun changement économique V1, nouvelle collecte ou partition réelle.

## 1. Baseline Git

Branche `d6-live-execution-staging`. HEAD initial / delivery au-dessus de 3b4a296 : `6f13bec5fd756a3ee79f1d593a26da020904e281`.
Le parent `3b4a296c2e603bfd513b3c70a6069cd832f6789d` et le delivery sont préservés.
Statut initial et log -5 dans [BASELINE.json](BASELINE.json). Trois modifications préexistantes exclues : les deux telemetry D5 et l'ancien REPORT.md harness. Les autres artefacts préexistants sont exclus.

## 2. Real V1 binding

**REAL_V1_BINDING_NOT_QUALIFIED**.
Résultat demandé B : **OBSERVABILITY_ONLY_V1_REVISION_REQUIRED**.
Le callback actuel omet l'entrée sur NO_EXIT_DEPTH/rotation et ne fournit pas tous les niveaux consommés. Un consommateur passif ne peut pas inventer ces événements.

## 3. Modification d'observabilité nécessaire

**YES**. Candidate explicitement versionnée `OBSERVABILITY_V1_R1`, dans observability_v2.py.
Le transformateur construit une AST séparée et ajoute uniquement des appels d'observation. Les fichiers protégés restent inchangés et aucune entrypoint réelle n'adopte cette candidate.
SHA de l'AST instrumentée : `ceaa1974edd442eedb94c038940cdcd0a8e987139b58a55316a8cc855680d6ef`.
Le recorder est synthétique, borné, non durable : sa présence n'est pas une liaison réelle qualifiée.

## 4. Preuve différentielle V1

[DIFFERENTIAL.json](DIFFERENTIAL.json) : PASS sur fixtures normale, sortie partielle, NO_EXIT_DEPTH et rotation ; mêmes données de fills, quantités, prix, résiduels, résultat simulé et attentes logiques [0.25, 0.5] seconde.
Fixtures de signal : mêmes décisions UP/DOWN/UP, même ordre et mêmes instants 200/1300/2500 ms ; seuil/lookback/cooldown intacts.
Retirer les seuls appels d'observation restitue exactement l'AST initiale.
La seule différence testée est l'ajout d'événements. Cela ne prouve pas un coût mural nul ni une intercalation asynchrone réelle inchangée ; aucune adoption n'a lieu.

## 5. Profondeur et réutilisation

PASS pour le **modèle prospectif existant**, sans modification de fill V1 :
10 shares visibles, première consommation 6, snapshot identique, seconde consommation 4, restant 0 ; recovery du journal conserve 0 ; troisième fill est rejeté sans append.
Le contre-exemple V1 reste matériel : V1 peut réutiliser sa profondeur affichée, mais le protocole exige le budget persistant. Le hook n'a pas le droit de redimensionner cette décision. Cette incompatibilité reste dans le blocker de liaison réelle.

## 6. Qualification des frais

**MARKET_FEE_UNQUALIFIED pour les deux tokens**.
Marché 4961058 : Gamma et CLOB concordent sur condition/token, feesEnabled=true, rate=0.07, exponent=1, takerOnly=true. Pas de qualification générale des futurs marchés.
[FEE_QUALIFICATION.md](FEE_QUALIFICATION.md), [FEE_SOURCE_AUDIT.json](FEE_SOURCE_AUDIT.json) et [FEE_QUALIFICATION.json](FEE_QUALIFICATION.json) lient sources officielles, retrieval et empreintes.

## 7. Arrondi / agrégation exacts

**UNPROVEN**, y compris partial fills et fills multiples. Le SDK testé expose un calcul de provision, pas l'arrondi final du match. Le contrat V2 inspecté reçoit les montants de frais ; sa liaison au marché étiqueté v1 n'est pas démontrée.
Exemple purement diagnostique : deux frais bruts 0.000035 donnent 0.00008 si arrondis séparément HALF_EVEN, contre 0.00007 après agrégation. Aucun choix arbitraire, aucune approximation appelée exacte et aucun fallback fee=0.

## 8. STORAGE_BREAKDOWN

[Tableau complet](STORAGE_BREAKDOWN.md), avec toutes les colonnes demandées ; [mesures JSON](STORAGE_BREAKDOWN.json).
**4 800 663 552 bytes attribués exactement, zéro page inconnue** :
- events : 2 551 357 440 bytes (53.145933 %) ;
- book_sides : 2 058 412 032 bytes (42.877657 %) ;
- reste : index, anchors, metadata et structure SQLite.
Profondeurs consécutives identiques : 455 086 lignes / 220 496 792 bytes, SOUS-ENSEMBLE non additif. Aucune suppression.
20 fichiers annexes totalisent 1 168 167 908 bytes HORS des 4.8 GB, dont metadata_projection.db 1 166 061 568 bytes.
Raw wire non isolé : ne pas assimiler les payloads stockés à une preuve de capture intégrale du transport.

## 9. Réduction lossless

**Appliquée au smoke technique uniquement**, pas au collecteur réel.
DDL et toutes les valeurs typées des tables sont conservées, y compris les BLOB compressés originaux, horodatages et doublons. Pas de sampling, drop ou agrégation économique.
La disposition physique des pages/index SQLite n'est pas préservée ; leur représentation logique l'est.
Cette conservation ne crée pas les observations V1/fees initialement absentes.

## 10. Mesure réelle du nouveau stockage

Fenêtre source complète : **1320.0542836000677 s**, aucun nouveau flux réseau.
Encodage : **633.244944 s**.
Archive : **336,113,918 bytes**, **254621.285030 bytes/s de fenêtre source**, ratio **14.282847**.
**3,973,286 lignes**, dont **1 336 887 événements**.
Framing/hashes/footer : **447,701 bytes**. Journal réel et checkpoint réel : non qualifiés, pas zéro.
Recovery/restitution exhaustive PASS ; SHA des deux flux logiques : `9b62642be7ae706a09637a8dd27f662e5ce2d0f96cdc259dcf76e711f92f0e30`.
Source ouverte immutable/read-only ; taille et mtime inchangés. Aucun résultat économique calculé sur cette capture.

## 11. Projection 168 h

Archive seule : **153,994,953,187 bytes**.
Marge déjà prescrite : **2× puis +20 %**.
Réserve minimale : **369,587,887,649 bytes**.
Projection sur le trafic observé 5m+15m ; ce n'est pas une mesure d'une future semaine 5m seule, ni une garantie de pic.

## 12. Espace nécessaire

Libre au terme du smoke : **47,701,286,912 bytes**.
Manque minimal : **321,886,600,737 bytes = 321.886600737 GB = 0.321886600737 TB**.
Le total exact qualifié est inconnu tant que les allowances journal/checkpoints sont inconnues.
**STORAGE_UNQUALIFIED**. Le disque supplémentaire seul ne fermerait pas les autres blockers.

## 13. Replay / mémoire

Archive streaming : **252.695122 s**, **15723.636 lignes/s**, pic **79,486,976 bytes**.
Ledger/journal synthétiques : recovery exact PASS à 101/1 001/5 001 événements ; copie d'état médiane environ 1.38/10.57/59.67 ms. Pic processus de la dernière étape : 45 551 616 bytes.
Le journal et accounting conservent O(N) historique ; observe recopie cet état. Le replay économique hebdomadaire reste **REPLAY_CAPACITY_UNPROVEN**.
[Mesures et limites](STORAGE_AND_REPLAY.md), [smoke](STORAGE_SMOKE.json), [probe](REPLAY_PROBE.json).

## 14. Tests ciblés

**18 PASS, 4 subtests PASS, 0 FAIL**. [Log](TARGETED_TESTS.log).
Observabilité/différentiel, profondeur et restart/reject, unknown fees et ambiguïté d'arrondi, exact roundtrip/compression, streaming/cache borné, fsync/disk-full et archive tronquée.
Une fixture initiale omettait la réservation de cash exigée par le ledger ; corrigée dans le test uniquement avant les suites finales.

## 15. Full suite

**980 PASS, 65 subtests PASS, 0 FAIL**.
Les **962 tests + 61 subtests** antérieurs sont conservés. 108 fichiers de test. Trois avertissements DuckDB existants.
[FULL_SUITE.log](FULL_SUITE.log), [VALIDATION.json](VALIDATION.json) avec empreintes de la clôture des sources testées.

## 16. Audit / leak scan

**PASS** pour le périmètre livré, distinct de READY.
Contrôle d'empreintes protégées, sources testées, revue des appels ajoutés, absence de mutation D6, scan PEM/tokens/literal private keys, gardes réseau et SDK. [AUDIT.json](AUDIT.json).
Le scan porte sur les nouveaux fichiers, pas sur une lecture de secrets préexistants.

## 17. Hashes BTC V1 avant / après

Identiques :
- paper_live.py : `5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364`
- run_d6_paper_live.py : `a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405`
- Genesis : `5365085da95cecb49fa4c922b890e9803ef223fdefef541505c2dc5a3de7814f`

## 18. Criteria hash avant / après

Identique : `869a386b9112a572247e3fb61ffbf4a27afb20493a791929e72f52bc0d9cd06a`.
72/48/48 h, embargo 60 s, FIXED25, signal 5 bps, lookback/cooldown, timing et critères économiques inchangés.

## 19. D6 inchangé

SYSTEM_READY=false, current_inventory_proven=false conservés. Aucun changement inventory, post-C, worker, Genesis, WS, CLOB readiness, risk ou D6_SEMANTIC_V1.
Il s'agit d'une conservation de l'état précédent, pas d'un nouvel audit de readiness.

## 20. Flags

REAL_ORDERS_ENABLED=false, LIVE_EXECUTION_ARMED=false, submit_allowed=false.
Aucune collecte réelle, aucun TRAIN/VALIDATION/OOS réel, aucun PAPER économique ou micro-live.

## 21. Monetary SDK attempts

**0**. 16 méthodes SDK gardées pendant les tests ; zéro connexion extérieure tentée par la suite. Trois tests de verrouillage appellent le wrapper de transport verrouillé, sans appel SDK monétaire.
Seuls des GET publics non authentifiés ont servi aux preuves de frais. Aucune clé privée, signature, ordre, cancel, transaction ou allowance update.

## 22. Commits

Ancêtres préservés : `3b4a296c2e603bfd513b3c70a6069cd832f6789d`, `6f13bec5fd756a3ee79f1d593a26da020904e281`.
Ce rapport est figé avant le nouveau commit séparé ; son SHA exact sera retourné dans la réponse de livraison après vérification.
Seuls les nouveaux fichiers de cette mission sont sélectionnés. Archive/smoke DB et fichiers préexistants sont exclus.

## 23. Push

À exécuter après commit et contrôles. Le statut effectif sera confirmé dans la réponse de livraison par comparaison HEAD / référence distante, pas supposé depuis le seul commit local.

## 24. Verdict exact

**BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED**.
Uniquement les blockers demandés encore démontrés :
1. REAL_V1_BINDING_NOT_QUALIFIED ;
2. MARKET_FEE_UNQUALIFIED ;
3. DISK_CAPACITY_UNPROVEN / DISK_SPACE_INSUFFICIENT, avec STORAGE_UNQUALIFIED et REPLAY_CAPACITY_UNPROVEN.

## 25. Commande de collecte

**Non fournie : pas READY. Aucune commande de collecte économique exécutée.**
