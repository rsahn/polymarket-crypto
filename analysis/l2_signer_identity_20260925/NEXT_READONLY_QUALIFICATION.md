# AUTHENTICATED_READ_ONLY — plan après preview L2 validé

État acquis : L2_PREVIEW_VALIDATED. L'utilisateur a confirmé le signataire historique 0x9348eFd557A09e644795C8F114BcF0BeF86F203a. Le preview confirmé du 25 septembre 2026 est sorti avec code 0, production Polygon 137, nonce 0. Son identité n'est plus un blocage. L'égalité historique déclarée signer/wallet ne constitue pas une règle générale ni une preuve du type de wallet actuellement utilisé par les endpoints.

Ce document remplace uniquement le constat NOT_CONFIGURED des anciennes notes. Les preuves historiques restent intactes. Il ne donne aucune autorisation de signature/récupération, d'ordre ou de mutation. Aucun réseau exécuté pour cette préparation.

## Prérequis de livraison
Le CLI de récupération reste preview-only. Avant toute récupération locale réelle : livrer et tester séparément la confirmation interactive après preview, la lecture tardive du stockage de clé existant, la limite d'une tentative GET de dérivation après GET time et le stockage exclusif DPAPI/ACL hors Git. Aucun create/bootstrap, fallback POST, retry automatique, scan ou déploiement. Les secrets restent locaux. La qualification ci-dessous consomme uniquement le triplet L2 existant, sans clé privée, et signe seulement le HMAC des GET.

Le passage du stockage protégé à la sonde doit être implémenté/testé : ne pas demander une copie des secrets dans la conversation, un argument CLI ou un fichier temporaire en clair. La sonde existante utilise des variables READONLY_* ; ce raccordement n'est pas encore attesté pour un stockage DPAPI. Rapport de chaque essai créé exclusivement, sans écrasement, sans headers, secrets, signatures ni réponses brutes sensibles.

## Ordre et critères des lectures
1. Collateral / balance / allowance : GET /balance-allowance avec type d'actif et signature type explicites. Établir contrat, chain, decimals et provenance; ne pas nommer USDC/pUSD sans preuve. Conserver montant raw et conversion Decimal séparément. Vérifier allowance/spender et capacité après conversion dans la même unité. Valeur ou identité ambiguë => BLOCKED.
2. Open orders : GET /data/orders, toutes les pages de la vue autorisée; conserver compteurs, fin de pagination, limites, doublons et erreurs expurgés. Une liste vide ne démontre pas l'absence globale d'ordres du wallet. Curseur répété, limite atteinte, erreur ou portée inconnue => complete=false.
3. Trades : GET /data/trades, pagination et portée temporelle/credential explicites, identifiants dédupliqués localement; distinguer entry fills, exit fills, annulations et fills tardifs. Absence dans une vue != preuve d'absence. Aucun cancel pour faciliter la qualification.
4. Positions / inventaire : GET Data API /v2/positions pour le wallet attendu, pagination entière de cette vue. Comparer aux balances conditionnelles GET /balance-allowance seulement pour les asset IDs/types démontrés. Recouper actifs issus du journal local, ordres, trades et indexeur. Un actif inconnu devient orphelin à réconcilier; cet ensemble ne prouve pas qu'aucun actif inconnu n'existe hors des vues accessibles.
5. Réconciliation : comparer snapshots datés, journal local et lectures distantes sans supposer une atomicité réseau. CLOSED local ne dispense pas de la politique distante; désaccord, lecture inaccessible, fill tardif, ordre ambigu ou inventaire résiduel => RECOVERY_REQUIRED et aucune nouvelle entrée. Aucune correction artificielle des quantités ni fermeture automatique.

Les routes de lecture d'un ordre individuel nécessaires à la réconciliation devront être ajoutées à l'allowlist de façon strictement validée avant utilisation, jamais par URL arbitraire. Pas de nouvelle route réseau implicitement autorisée par ce plan.

## Verdict et frontière
Produire un rapport de qualification expurgé avec provenance, horodatage, types/unités, pagination, portée et motifs pour chaque contrôle. complete=false partout où l'exhaustivité globale n'est pas démontrée, même après HTTP 200 et pagination terminée. Aucun fallback optimiste.

La cohérence de ces GET qualifie les lectures; elle ne suffit pas à rendre l'exécution prête. Restent notamment : exhaustivité/réconciliation, carnet synchronisé et frais (REST seul insuffisant), geoblock récent, risque de session réel, inventaire, recovery local, contrat de sortie, et tous les contrôles ProductionReadinessCheck. Aucune date ni verdict de production acquis avant preuves.

REAL_ORDERS_ENABLED=false; LIVE_EXECUTION_ARMED=false; transport monétaire hard-locked; aucun raccordement au runner; BTC V1 inchangée. Toute frontière d'exécution reste distincte et soumise au feu vert utilisateur.
