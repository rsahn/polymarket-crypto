# D6 — diagnostic du 25 septembre 2026

Le diagnostic et les tests hors réseau sont terminés. L'attribution exacte des délais du run cible reste à mesurer : `POLYGON_ARCHIVE_RPC_URL` est absent de l'environnement de cette tâche et du `.env` du dépôt. Aucun endpoint de remplacement n'a été inventé. Aucun run réseau cible n'a été lancé.

## Résultats démontrés et limites

Rapport de référence : `D6_POST_GENESIS_READINESS_20260925_173424_838443.json`, code initial `1392c9e`.

| Intervalle | Mesure historique | Ce que la mesure établit |
|---|---:|---|
| Fin worker scan → reprise | 176 ms | Attente après la fin du scan ; cause non tracée dans ce rapport |
| Résultat génération → reprise runner | 137 ms | Attente après le résultat ; cause non tracée |
| Account | 844 ms | Dernier GET terminé 454 ms avant la fin de phase ; requête la plus longue 385 ms |
| Rechecks B/C | 623 ms | Dernier RPC terminé 371 ms avant la fin de phase ; RPC le plus long 249 ms |
| Fin réconciliation → évaluation | 156 ms | Inclut notamment l'attente des sources readiness ; attribution à mesurer |
| Dernier rejet WS | âge 500 → 501 ms | Le message était déjà à la limite à réception applicative, puis le contrôle l'a refusé ; seuil respecté |
| Âges inventory / account à évaluation | 2 393 / 1 765 ms | Sources périmées ; aucune réinterprétation des timestamps |

Les durées des requêtes mesurent du temps de worker, pas une mesure isolée du réseau. La « réception » WS est la reprise de `recv()` dans l'application, pas l'arrivée au noyau. Ces données ne prouvent ni un problème de GIL, ni une cause réseau, ni une cause unique asyncio.

La copie intégrale des carnets dans `ingest()` est un coût CPU démontré. La correction locale préexistait à cette intervention et a été commitée pendant celle-ci dans `801dbc2`. Elle conserve le prédicat de synchronisation et les copies détachées au moment de la lecture décisionnelle. Je l'ai conservée et remesurée, sans ajouter d'autre optimisation de latence spéculative.

Benchmark reproductible hors réseau, deux passages par variante, 2 000 deltas, 198 niveaux par carnet, horloge de fraîcheur fixe, sans profiler :

| Variante | Durée lot | CPU du thread | Reprise worker déjà terminé |
|---|---:|---:|---:|
| `1392c9e`, passage 1 | 3 608,8 ms | 3 609,4 ms | 3 596,0 ms |
| Copies supprimées, passage 1 | 1 394,6 ms | 1 390,6 ms | 1 387,8 ms |
| `1392c9e`, passage 2 | 3 715,6 ms | 3 656,3 ms | 3 703,4 ms |
| Copies supprimées, passage 2 | 1 377,4 ms | 1 375,0 ms | 1 358,0 ms |

Cette expérience force un lot synchrone sans yield pour démontrer le mécanisme et mesurer le coût de la copie. Elle ne reproduit pas la distribution des frames du run historique, ne valide pas la fraîcheur en temps réel et ne prouve pas que chacun des délais historiques vient du WS. Les timings cible après changement sont **à mesurer**.

## Changements de cette intervention

- `backend/app/live/latency_trace.py` : diagnostic activé explicitement, mémoire bornée à 20 000 événements avec compteur des événements perdus ; horloge monotone et ancre UTC ; attente avant worker, durée worker, reprise ; CPU uniquement autour de code synchrone ; sonde de retard de boucle toutes les 10 ms. Aucun argument, payload, header ou credential enregistré.
- `network_readonly.py` et `qualify_post_b_proofs.py` : instrumentation des GET, sélection C, scan, seal, et rechecks B/C ; phases account et recheck. Les appels et leur ordre causal restent identiques.
- `generation_worker.py` : marqueurs monotones résultat prêt / runner repris. Aucun nouveau modèle de scheduling.
- `readonly_book_stream.py` : mesure du décodage et de chaque ingestion, sans changement des règles de parsing, timestamps, invalidation ou resynchronisation.
- `readiness.py` : mesure de l'attente groupée des sources, sans déplacement des contrôles.
- `qualify_post_genesis.py` : option `--diagnostics`, chronologie de chaque composant account, et champ indépendant `inventory_completeness`.
- Tests : cinq nouveaux cas de diagnostic/complétude. Correction d'une assertion non déterministe qui exigeait C avant B alors que les deux RPC sont parallèles depuis les commits précédents. L'assertion vérifie maintenant sélection → seal → account terminé → les deux rechecks, dans n'importe quel ordre interne.
- `analysis/latency_diagnostic_20260925/` : logs RED/GREEN, suite complète, audit, benchmark reproductible et synthèseur des chevauchements WS/délais.

Le synthèseur rapporte séparément le temps WS observé à l'intérieur des attentes et le CPU des segments entièrement inclus. Il ne transforme pas un chevauchement en preuve de causalité exclusive. Les résultats doivent être interprétés avec le compteur d'événements perdus et l'effet de l'instrumentation elle-même.

## Complétude post-C, problème indépendant

`evaluate_boundary` prouve une couverture CTF jusqu'à C. Les vues account/indexer n'apportent pas de watermark commun prouvant l'absence d'activité après C. Même avec une génération fraîche et tous les composants complets, `current_inventory_proven` reste faux et la raison est `POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN`.

Si la génération est périmée, la raison principale devient `GENERATION_STALE_500MS`, mais la limitation de complétude demeure. Le nouveau champ la rend visible simultanément. Les tests vérifient les deux cas sans rajeunir les preuves et sans modifier `fixed_boundary.py`. Une réduction de latence seule ne peut donc pas produire SYSTEM_READY.

## Tests et audit

- RED instrumentation : 3 échecs attendus avant ajout du module.
- RED complétude : 2 échecs attendus avant ajout du diagnostic indépendant.
- GREEN ciblé final : 44 tests réussis.
- Suite complète finale : **713 passed, 25 subtests passed, 3 warnings**, en 37,97 s. Les avertissements concernent une API DuckDB dépréciée.
- Première exécution confinée : dépendances PyArrow/DuckDB invisibles. Exécution avec accès aux dépendances locales : un test révélait l'ordre interne non déterministe B/C ; corrigé puis suite complète repassée.
- Audit AST : **AUDIT_OK**, 114 fichiers, appels monétaires confinés au transport verrouillé.
- Harnais : 0 connexion externe tentée, 0 tentative SDK monétaire, 16 méthodes SDK protégées. Trois appels du transport sont les tests du refus inconditionnel, sans accès SDK.
- `git diff --check` sur les fichiers modifiés : aucun problème d'espacement.

Commande de la suite :

```powershell
python analysis/validate_execution.py backend/tests tests analysis/d5/auditor_next analysis/d51/test_review51.py analysis/d6/tests analysis/d6/pipeline analysis/d6/research analysis/d6/paper_runtime analysis/test_c3_d4_analysis.py
python analysis/audit_live_boundary.py
```

## Invariants

Seuil 500 ms inchangé ; aucun rajeunissement ; account avant les rechecks B/C ; aucune suppression de contrôle ; fixed-C inchangé ; Genesis et BTC V1 inchangés. Aucun ordre, transaction, appel SDK monétaire ou passage en réel. Les deux flags du `.env` sont confirmés `false` et le harnais les force à `false`. Les fichiers `fixed_boundary.py`, `genesis_ledger.py`, `production_readonly.py` et `analysis/d6/paper_live.py` n'ont aucun diff depuis `1392c9e`. Aucun accès réseau cible ni modification du ledger Genesis par cette intervention.

## Prochain run cible exact

À exécuter dans une session où le RPC archive validé du run précédent est déjà configuré. Ne pas publier sa valeur dans le rapport ou la conversation.

```powershell
Set-Location 'C:\Users\Ramy\Documents\polymarket-crypto'
$env:REAL_ORDERS_ENABLED = 'false'
$env:LIVE_EXECUTION_ARMED = 'false'
if (-not $env:POLYGON_ARCHIVE_RPC_URL) { throw 'RPC archive du run précédent non configuré' }
python analysis/qualify_post_genesis.py --target-machine --health-contract --diagnostics
```

Le runner conserve les GET authentifiés et les RPC de lecture autorisés ; aucun transport monétaire n'est raccordé. Il peut publier un checkpoint de curseur vérifié, comme auparavant, mais ne crée ni ne modifie Genesis dans ce mode. Le JSON produit permet d'attribuer les attentes au niveau applicatif. Utiliser ensuite `python analysis/latency_diagnostic_20260925/summarize_latency.py <chemin_du_nouveau_rapport.json>` pour lire les chevauchements mesurés.
