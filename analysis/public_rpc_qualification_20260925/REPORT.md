# D6 — alternative RPC mesurée et lancement reproductible

La fraîcheur d'inventaire passe sous 500 ms sur deux nouveaux runs réels : **421 ms puis 409 ms**, contre 817 ms dans le rapport précédent. Aucun contrôle, test ou timestamp n'a été supprimé ou assoupli. Cela ne valide pas SYSTEM_READY : la complétude post-C reste non prouvée et le second run a rejeté un carnet WS en régression.

## Diagnostic et choix

Référence avant : `D6_POST_GENESIS_READINESS_20260925_182648_494531.json`. Deux requêtes `eth_getLogs` avaient chacune duré 497 ms malgré la réutilisation des connexions.

Un benchmark local de huit tâches sans I/O, sur 200 passages, mesure 0,705 ms de médiane pour créer/détruire le pool contre 0,164 ms pour le réutiliser (p95 : 0,776 contre 0,191 ms). Le gain synthétique de 0,541 ms ne traite pas le dépassement de 317 ms. Aucune complexité de cache ou de pool supplémentaire n'a donc été ajoutée. Les tests ne s'exécutent pas dans le runner cible : les alléger ne réduirait pas son temps.

Le RPC public déjà référencé dans le code, `https://polygon.drpc.org`, a été testé séparément par sept lectures publiques, sans credentials ni changement du runner. Les quatre lectures de logs ont pris 109, 142, 115 et 106 ms, avec un hash de borne inchangé. Passer de dix blocs à un bloc n'a pas montré d'amélioration constante ; les fenêtres du scanner sont conservées.

Deux runs D6 complets ont ensuite utilisé explicitement ce fournisseur dans l'environnement de leur processus. Toutes les vérifications originales ont été exécutées, y compris les lectures account authentifiées de lecture seule. Aucun changement du `.env`, aucune substitution automatique après erreur, aucune nouvelle source de timestamps.

## Résultats réels

| Mesure | Avant, 18:26:48 UTC | Public, 18:38:00 UTC | Public, 18:39:03 UTC |
|---|---:|---:|---:|
| Âge inventory à évaluation | 817 ms | **421 ms** | **409 ms** |
| Âge account | 248 ms | 206 ms | 185 ms |
| Âge book utilisable | 46 ms | 49 ms | Aucun : BOOK_REGRESSION |
| Chemin critique depuis dispatch scan | 892 ms | 511 ms | 507 ms |
| Génération bornée complète | false | **true** | **true** |
| Current inventory proven | false | false | false |
| SYSTEM_READY | false | false | false |
| MARKET_ELIGIBLE_NOW | true | true | false |
| RPC réussis | 55/55 | 73/73 | 32/32 |
| Submit allowed | false | false | false |

Le chemin critique inclut le contrôle du curseur avant le début de l'observation du scan ; ce n'est pas le champ auquel est appliqué le seuil de fraîcheur. Le code et la définition des timestamps restent identiques. Les âges inventory ci-dessus sont ceux des rapports, sans recalage.

Sur le premier run public complet, les logs finaux ont pris 113 et 116 ms. La comparaison n'est pas simultanée : charge, blocs et conditions réseau peuvent différer. Deux succès ne prouvent pas un percentile de latence ni une disponibilité future.

## Blocages conservés

- **Post-C** : `POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN` reste le verdict de réconciliation. Une génération bornée fraîche ne démontre toujours pas la complétude après C.
- **WS du second run** : un full book du même token porte 1790361542729 après un full book déjà accepté à 1790361542735, soit **−6 ms**. Il a été rejeté avant mutation et le flux a été déconnecté selon les règles existantes. Aucun message en régression n'a été accepté et aucun timestamp retouché.
- Flags `REAL_ORDERS_ENABLED=false`, `LIVE_EXECUTION_ARMED=false`, `submit_allowed=false` sur les deux runs. Genesis inchangé, aucune clé privée chargée. Aucun ordre, transaction ou appel SDK monétaire effectué.

## Livraison

`analysis/run_d6_public_readiness.ps1` fournit le lancement explicite sur ce RPC public, force les deux flags à false et restaure la valeur précédente de `POLYGON_ARCHIVE_RPC_URL` à sa sortie. Il ne modifie pas le `.env`. Le moteur, les contrôles, le seuil 500 ms, Genesis, BTC V1, fixed-C et les règles WS sont inchangés.

Commande exacte, depuis n'importe quel répertoire PowerShell :

```powershell
& 'C:\Users\Ramy\Documents\polymarket-crypto\analysis\run_d6_public_readiness.ps1'
```

Cette commande lance uniquement le diagnostic complet de lecture seule. Son succès d'exécution ne signifie pas que SYSTEM_READY est vrai ; consulter le JSON produit.

Les rapports des deux runs, le benchmark, la sonde publique et l'audit sont conservés avec cette livraison. Aucun test n'a été allégé. La syntaxe du lanceur PowerShell est validée et le lanceur a été exécuté pour le second run réel.

Suite complète exécutée : **725 tests et 25 sous-tests réussis**, 39,72 s ; trois avertissements DuckDB de dépréciation. Audit AST : **AUDIT_OK**, 116 fichiers, transport monétaire verrouillé. Le harnais hors réseau indique zéro tentative de connexion externe et zéro tentative SDK monétaire. Les deux runs réels sont des diagnostics séparés de cette suite hors réseau.
