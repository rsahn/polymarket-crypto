# D6 — démarrage des connexions et preuve post-C

Référence : `D6_POST_GENESIS_READINESS_20260925_182006_498792.json`, base `786be04`.

## Ce qui est mesuré

Le run a réussi ses 202 RPC sans 429. Inventory reste âgé de 679 ms au moment de la décision : environ 317 ms depuis le début du scan jusqu'à account, 271 ms pour account, 81 ms pour B/C et 10 ms jusqu'à l'évaluation. Les reprises sont désormais courtes : scan 1 ms, génération 0 ms dans les compteurs entiers. Account est âgé de 362 ms ; le carnet est synchronisé et âgé de 51 ms.

Les cinq requêtes RPC parallèles avec nouvelle connexion TCP/TLS durent 232–243 ms. La lecture de chaîne qui réutilise la connexion dure 75 ms ; les rechecks B/C réutilisés durent 74–80 ms. Les quatre GET account démarrent tous une nouvelle connexion : 151, 156, 159 et 266 ms. L'ouverture de connexions dans le chemin critique est donc attestée. Le coût exclusif du handshake n'est pas isolé : on ne peut pas attribuer toute la différence de durée au transport ni promettre un gain précis.

## Changement livré

Avant le démarrage WS et la sélection de C, lorsque les pools persistants sont disponibles :

- Une génération de lectures account prépare les connexions CLOB/Data. Ses résultats sont jetés.
- Huit lectures publiques `eth_chainId`, chacune validée sur Polygon, exercent le pool RPC borné à huit connexions.
- Aucun retry, nouvelle route HTTP, SDK monétaire ou cache de preuve n'est ajouté.
- Toutes les lectures de décision sont ensuite exécutées de nouveau : scan/seal, account, rechecks B/C dans l'ordre initial. Leurs timestamps réels sont conservés.
- En cas d'erreur ou d'annulation, les lectures préparatoires sont drainées avant fermeture des pools. Une erreur empêche la suite.
- Sans pools persistants, la préparation est explicitement indiquée comme non applicable ; aucune preuve de réutilisation n'est inventée.

Le rapport inclut `connection_warmup`, avec le nombre de lectures et la mention explicite que la réutilisation n'est pas garantie. Les traces de connexion des requêtes finales permettront de mesurer l'effet réel. Cette préparation ne remplace aucun contrôle du scan final et ne modifie pas le limiteur de rattrapage.

## Pourquoi post-C demeure bloqué

Le code connecté prouve l'inventaire CTF jusqu'à C. Ses vues account et indexer sont acquises après C sans certificat de complétude commun. Un transfert externe après C peut donc ne pas être couvert par le scan borné à C, ni encore visible dans l'indexer. Une nouvelle lecture du hash de C ne couvre pas ce transfert.

La documentation officielle du [flux utilisateur](https://docs.polymarket.com/trading/realtime-order-updates) le décrit comme un flux d'ordres et de trades du compte authentifié. Le contrat consulté ne donne pas une attestation commune des transferts CTF et du snapshot d'inventaire. La [Data API v2](https://data-api.polymarket.com/v2/docs) documente la pagination des résultats ; cela ne constitue pas, à lui seul, une preuve commune de complétude après C. Cette conclusion concerne les sources et garanties examinées, pas toutes les sources qui pourraient exister.

Il manque un fournisseur de preuve qui relie de manière vérifiable un snapshot, l'ensemble des événements pertinents après sa borne et une borne de complétude au moment de la décision. Ajouter un abonnement sans garantie de reprise/séquence, voir un compte vide, ou constater un hash C inchangé ne suffit pas. Une source capable d'apporter cette garantie doit être identifiée et son contrat testé avant de remplacer ce refus. Aucun tel certificat n'a été obtenu dans cette intervention.

`current_inventory_proven=false` est donc conservé. Il n'est pas possible d'annoncer les deux points débloqués sous les invariants actuels. Le seuil 500 ms, fixed-C, Genesis, BTC V1 et les règles WS restent inchangés.

## Validation et limites

RED : quatre échecs avant ajout du module. GREEN ciblé : 62 tests réussis. Six nouveaux tests couvrent les lectures publiques seules, le rejet des mauvais résultats, les données account jetées, les lectures finales fraîches, le drainage sur erreur et l'annulation.

Suite complète : **725 tests et 25 sous-tests réussis** en 40,42 s ; trois avertissements DuckDB de dépréciation. Audit : AUDIT_OK, 116 fichiers, verrous monétaires préservés. Harnais : zéro connexion externe tentée et zéro tentative SDK monétaire. Aucun ordre ni transaction. Flags live `false`.

Après sur cible : **à mesurer**. Le RPC archive est toujours absent de l'environnement de cette tâche et du `.env` ; aucun nouveau run cible n'a été effectué. Les pools peuvent expirer ou ne pas réutiliser toutes les connexions ; les appels supplémentaires restent soumis aux limites fournisseur. Une baisse sous 500 ms reste à établir sur le prochain rapport et ne résoudra pas à elle seule le manque de preuve post-C.

## Prochain run

Dans la session où le RPC archive précédent est configuré :

```powershell
Set-Location 'C:\Users\Ramy\Documents\polymarket-crypto'
$env:REAL_ORDERS_ENABLED = 'false'
$env:LIVE_EXECUTION_ARMED = 'false'
if (-not $env:POLYGON_ARCHIVE_RPC_URL) { throw 'RPC archive non configuré' }
python analysis/qualify_post_genesis.py --target-machine --health-contract --diagnostics
```

Vérifier `connection_warmup`, les connexions réutilisées des requêtes finales, `final_timing_budget` et `inventory_completeness`. Aucune activation live n'est autorisée par cette correction.
