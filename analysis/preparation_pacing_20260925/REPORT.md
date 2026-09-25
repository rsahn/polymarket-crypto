# Correction du run D6 du 25 septembre 2026 à 18:00:18 UTC

Rapport analysé : `D6_POST_GENESIS_READINESS_20260925_180018_402488.json`.

## Causes établies

- La préparation émet 114 RPC, dont 104 `eth_getLogs` en une fenêtre de 1 110 ms. Deux requêtes reçoivent HTTP 429, sur les plages 94436034–94436043 et 94436044–94436049. Le scan échoue donc avant le chargement account et avant le démarrage WS. Ce rapport ne constitue pas une nouvelle mesure de leur latence.
- Après cet échec, le runner réutilise les métadonnées du curseur sauvegardé. Les 176 ms et les anciens timestamps account/recheck appartiennent au run précédent. Le budget affiché de 1 558 175 ms est un intervalle entre deux runs, pas le chemin critique du nouveau run.
- Le JSON ne contient pas `latency_diagnostics`. Aucun diagnostic GIL, asyncio ou réseau détaillé n'est inféré à partir des anciens timings.

## Correction appliquée

`PreparationRPC` enveloppe seulement la préparation de l'inventaire : une requête en vol, au moins 200 ms entre débuts de requêtes (au maximum cinq départs par seconde en moyenne), aucun retry, budget de démarrage de 120 secondes. Une requête déjà en cours conserve son timeout existant. Cette politique prudente supprime la rafale ; elle ne prétend pas connaître le quota du fournisseur ni garantir l'absence de futurs 429.

La préparation conserve toutes les plages de dix blocs, les lectures de chaîne/code, les contrôles de hashes et le témoin numérique final. La sélection finale C, account et les rechecks B/C utilisent le RPC original : leur parallélisme interne et leur ordre causal sont inchangés. Aucun changement de Genesis, BTC V1, fixed-C ou règles WS.

Un 429 arrête les lectures avec `PREPARATION_RPC_RATE_LIMITED`. Aucun nouveau curseur n'est publié sur scan incomplet. Le budget épuisé donne `PREPARATION_RPC_BUDGET_EXCEEDED`. Aucun contournement, résultat partiel accepté ou rajeunissement de timestamp.

Le runner distingue maintenant l'inventaire de génération courante des données de préparation/curseur. Sans nouvelle génération : timings courants à `null`, anciennes preuves non exposées comme courantes, `inventory_evidence_origin=PREPARATION_OR_PRIOR_CURSOR`. Le timestamp réel du curseur est conservé.

Le blocage distinct `current_inventory_proven=false` demeure : la correction ne fournit pas de watermark commun de complétude post-C.

## Validation

RED : quatre échecs avant correction, dont la reproduction exacte du faux délai 176 ms. GREEN ciblé : 58 tests réussis. Six nouveaux tests couvrent l'espacement, l'arrêt sur budget, le refus 429 sans retry, la séparation des anciens timings, le scan réel simulé de 1 036 blocs avec ses 104 plages et le rapport d'échec avant account.

Suite complète : **719 tests et 25 sous-tests réussis** en 49,01 s ; trois avertissements DuckDB de dépréciation. Audit AST : **AUDIT_OK**, 115 fichiers, transports monétaires verrouillés. Harnais : zéro connexion externe tentée, zéro tentative SDK monétaire, 16 méthodes SDK protégées. Les logs sont livrés dans les fichiers associés. Les deux flags du `.env` restent `false`.

## Mesures restantes

Avant : 104 requêtes de logs sur 1 110 ms, deux HTTP 429 ; génération finale non démarrée.

Après sur cible : **à mesurer**. Le RPC archive n'est pas configuré dans l'environnement de cette tâche ni dans le `.env` ; aucun run cible n'a été lancé. Le scan simulé vérifie l'espacement et la couverture complète, pas le quota réel du fournisseur. Un retard trop important du curseur peut dépasser le budget et restera bloquant.

## Prochain run exact

Dans la session possédant déjà le RPC archive du run précédent :

```powershell
Set-Location 'C:\Users\Ramy\Documents\polymarket-crypto'
$env:REAL_ORDERS_ENABLED = 'false'
$env:LIVE_EXECUTION_ARMED = 'false'
if (-not $env:POLYGON_ARCHIVE_RPC_URL) { throw 'RPC archive non configuré' }
python analysis/qualify_post_genesis.py --target-machine --health-contract --diagnostics
```

Aucun ordre, transaction, appel SDK monétaire ou passage en réel n'a été effectué.
