# Divergences read-only — audit du 25 septembre 2026

## Balance ancien/nouveau
Diagnostic machine expurgé : REQUEST_DIAGNOSTIC.json. Aucune lecture de credential/clé privée et aucun GET de compte pendant cet audit. Les paramètres historiques sont reconstruits à partir du code pre_live_check_d6.py et du SDK 0.11.0 installé, pas d'une capture HTTP historique. La valeur 109160000 est attestée ici par le rapport utilisateur, pas par une nouvelle mesure.

| Élément | Ancien pre-live (code inspecté) | Sonde actuelle |
|---|---|---|
| Environnement | PRODUCTION par défaut, Polygon 137 | production Polygon 137 |
| Route / méthode | GET /balance-allowance | identique |
| asset_type | COLLATERAL | COLLATERAL |
| asset_id / token_id | absents | absents |
| POLY_ADDRESS | signataire EOA confirmé | même signataire confirmé |
| wallet | omis au constructeur ; SDK résout Deposit Wallet | adresse du signataire passée comme wallet |
| signature_type envoyé | 3 (Deposit Wallet) | 0 (EOA) |
| wallet / spender dans query | aucun | aucun |
| allowance examinée | ancien rapport expose la map allowances | sélection du Standard Exchange dans cette map |
| raw observé | 109160000, historique fourni | 0, rapport cible fourni |

Le SDK _resolve_requested_wallet vérifie historiquement le déploiement UUPS via relayer puis choisit UUPS ou beacon. Ce chemin n'a pas été exécuté. Les deux adresses candidates du diagnostic sont seulement calculées hors réseau à partir de l'adresse PUBLIQUE ; ni déploiement, ni propriété distante, ni solde prouvés. Le log historique SIGNER=POLYMARKET_WALLET ne démontre pas le wallet finalement résolu dans le contexte SDK lorsque wallet est omis.

Différence de sélection démontrée : 0 contre 3. Elle rend les lectures non comparables et constitue une explication technique plausible du 0, pas une preuve que le solde du Deposit Wallet vaut encore 109160000. Aucun changement silencieux de wallet ou de signature_type, aucun scan, aucune lecture de remplacement automatique. Pour clôturer : qualification locale distincte du GET exact signature_type=3, puis identification attestée du Deposit Wallet réellement utilisé ; pas de constructeur SDK ni relayer mutateur. Ne pas assimiler les deux allowances sélectionnées sans vérifier leur spender.

Sources SDK inspectées : clients/async_secure.py create (production/wallet=None), _resolve_requested_wallet, get_balance_allowance, _make_l2_header_resolver ; _internal/actions/account.py build_balance_allowance_request ; _internal/wallet.py signature_type_for. L'adresse wallet n'est PAS envoyée directement à /balance-allowance. Le contexte signer + signature_type fait partie de la sélection serveur. HMAC GET sur timestamp+méthode+chemin, sans paramètres de query, dans les deux chemins.

## Collateral
Le SDK PRODUCTION_CONFIG annonce le contrat 0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB, identifié comme pUSD dans la documentation officielle. Cela prouve la concordance configuration/documentation, pas une lecture on-chain ni l'actif effectivement associé à chaque réponse historique.

- symbol_verified=false : aucune lecture du symbole du contrat exécuté ; documentation distinguée de preuve réseau.
- decimals_verified=false : /balance-allowance ne retourne pas de decimals et aucune lecture du contrat n'a été effectuée.
- account_binding_verified=false : réponse sans attestation du contrat/wallet sélectionné, divergence EOA/Deposit Wallet non réconciliée.

Ces flags sont des blocages intentionnels, pas des bugs. Aucun raw converti. L'ancienne division constante par 1000000 ne sert pas de preuve. Aucune modification d'allowance ni route /balance-allowance/update appelée (cette route peut muter malgré GET).

## Positions HTTP 400
Route documentée inchangée : /v2/positions ; le guide officiel confirme les curseurs opaques et l'enveloppe data/pagination. SDK list_positions_spec génère user, filter_type=TOKENS, filter_amount=0, include_archived bool, puis limit=100 et cursor si nécessaire. full_history=True n'ajoute aucun paramètre de date pour positions, déjà non bornées par défaut. Le filtre de lifecycle par défaut reste OPEN, donc pas une histoire exhaustive des positions clôturées.

BUG REPRODUIT : urllib.urlencode émettait include_archived=True ; le SDK/httpx émet include_archived=true. RED conservé, correctif minimal de sérialisation des booléens, GREEN. Aucun renommage de champ, suppression de filtre ou fallback v1. Les autres paramètres correspondent au SDK installé. Le schéma OpenAPI v2 lié par la documentation n'était pas accessible via l'outil web ; aucune contrainte supplémentaire inventée.

IMPORTANT : le test prouve le défaut de parité du contrat SDK sur le fil. Sans corps d'erreur expurgé ni nouvelle observation cible, il ne prouve PAS que cette différence était la cause unique du HTTP 400. Résultat réseau après correction non mesuré. Si 400 persiste, garder BLOCKED et recueillir uniquement un code/nom de paramètre expurgé.

## Réconciliation locale
Aucune valeur READONLY_EXECUTION_STATE_DB dans le processus. Dans le code applicatif inspecté, aucun appel au constructeur ExecutionStore hors tests ; le runner monétaire n'est pas raccordé. Aucune base live autoritative identifiée. Les DB d'analyse/replay/collecte ne sont pas un ledger live et ne sont pas réutilisées.

Contrat réel attendu : ExecutionStore, tables execution_state (id=1,value JSON) et execution_events (transitions). BUG REPRODUIT dans le lecteur : il exigeait open_shares, alors que l'état réel persiste bought/sold. RED avec état réel RECOVERY_REQUIRED, bought=5/sold=2 ; correction : reliquat bought-sold, quantités finies non négatives, sold<=bought, phase reconnue, CLOSED avec reliquat non nul rejeté. Aucun changement du store, du contrôleur, de BTC V1 ni d'une DB réelle.

Initialisation future : identifier un chemin dédié et le wallet réel, conserver les snapshots distants datés et le journal de provenance, établir ordres/inventaire/règlements de départ avant toute initialisation opérationnelle. En absence de preuve exhaustive, conserver UNKNOWN/RECOVERY_REQUIRED au niveau de l'initialisation ; ne pas écrire CLOSED/FLAT pour satisfaire un test. Désigner ensuite explicitement READONLY_EXECUTION_STATE_DB. L'initialisation doit aussi définir les bornes du risque de session et l'historique externe importé. Rien de cela n'est créé ici.

## Ce que les zéros prouvent
Les GET /data/orders et /data/trades authentifiés ont renvoyé des vues vides, avec fin de pagination, pour le credential et les paramètres employés à cet instant. Le SDK n'ajoute ici aucun filtre asset/market/maker/date, mais cela ne démontre pas la portée historique globale du serveur, des autres credentials, wallets ou sessions. Aucun signature_type=0 n'est envoyé à ces routes : ne pas attribuer automatiquement leur vacuité au seul défaut de signature_type de balance. Zéro ordre ouvert != zéro ordre historique ; zéro trade dans cette vue != zéro inventaire acquis autrement. complete=false.

## Sources publiques consultées (documentation uniquement)
- https://docs.polymarket.com/trading/wallets-auth : wallets EOA/Deposit et contrats d'approval.
- https://docs.polymarket.com/resources/contracts : contrats publics.
- https://docs.polymarket.com/concepts/pusd : dénomination documentaire.
- https://docs.polymarket.com/migrate/data-api-v1-to-v2 : /v2/positions, lifecycle et pagination.
- https://data-api.polymarket.com/v2/openapi.json : lien officiel identifié mais consultation indisponible.

Flags false, transport monétaire hard-locked, aucune dérivation L2, aucune clé privée/signature L1, aucun ordre/cancel/update allowance. BTC V1 inchangée.

## Validation finale
Suite projet hors dependances vendor : 446 passed, 25 subtests passed, 0 failed, 0 errors, 3 warnings. Audit statique : 95 fichiers, AUDIT_OK, monetary_methods_hard_locked=true. OFFLINE_PROOF : sdk_monetary_attempts=0, 16 methodes gardees, deux flags false. Deux regressions RED/GREEN conservees (boolean HTTP et schema ledger), plus test de diagnostic identitaire. Diff BTC V1 contre 4cb928c vide. Aucune qualification distante nouvelle executee.
