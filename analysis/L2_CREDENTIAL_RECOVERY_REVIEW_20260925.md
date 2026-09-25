# Credentials CLOB L2 : récupération et initialisation contrôlée

Étude statique polymarket-client 0.11.0 et documentation officielle, 25 septembre 2026. Aucun appel réseau authentifié, aucune clé privée lue/utilisée, aucune signature générée, aucun credential créé/dérivé. Seules les pages publiques de documentation ont été consultées. Aucun changement BTC V1, .env, flags ou transport monétaire.

## Conclusion
Une récupération distante d'un jeu EXISTANT est documentée via GET /auth/derive-api-key, mais elle exige une signature L1 EIP-712 ClobAuth du signataire et le nonce concerné. Cette opération est nommée dérivation; elle n'est pas la création POST et n'est pas une reconstitution locale hors réseau. Elle demeure interdite dans la phase présente. Sans signature L1 ni triplet L2 connu, aucune voie documentée ne permet de retrouver secret/passphrase à partir d'une simple adresse ou API key.
L'absence de mutation du credential existant est le contrat documenté de ce GET, pas une preuve expérimentale de l'implémentation serveur ni une absence absolue de logs/rate-limit côté serveur.

## Matrice exacte
| Opération | SDK 0.11.0 | Endpoint HTTP | Authentification | Résultat / effet |
|---|---|---|---|---|
| Identifier les clés | AsyncSecureClient.fetch_api_keys(), action interne auth.fetch_api_keys(secure_clob) | GET /auth/api-keys | L2 HMAC-SHA256, triplet déjà connu | tuple[str,...] d'identifiants, pas secret/passphrase; lecture |
| Récupérer/dériver un triplet existant | action interne polymarket._internal.actions.auth.derive_api_key(clob, signature) | GET /auth/derive-api-key | L1 EIP-712 ClobAuth, address/timestamp/nonce/signature | ApiKeyCreds(apiKey,secret,passphrase), jeu existant pour signataire+nonce; aucun fallback POST dans cette fonction |
| Créer un nouveau jeu | action interne auth.create_api_key(clob, signature) | POST /auth/api-key | L1 EIP-712 | création serveur; mutation explicitement interdite ici |
| Créer ou dériver | action interne auth.create_or_derive_api_key(clob, signature) | POST /auth/api-key puis GET /auth/derive-api-key uniquement sur HTTP 400 | L1 | ne constitue PAS un bootstrap read-only; exclu |
| Authentifier une lecture connue | _make_l2_header_resolver(signer, credentials); build_hmac_signature(secret,timestamp,method,path,body) | GET /balance-allowance, /data/orders, /data/trades | HMAC à partir du secret; adresse publique, API key, passphrase et timestamp | pas de signature EVM ni clé privée nécessaires au protocole L2; aucun changement du credential |

Méthodes internes: implementation inspectée, pas promesse d'API publique stable. Ne pas utiliser AsyncSecureClient.create pour accéder à ces fonctions: _bootstrap_credentials peut créer une clé, puis _ensure_wallet_ready peut déployer un deposit wallet absent. Même fournir des credentials au constructeur n'élimine pas tous ses effets potentiels. Les helpers purs doivent être isolés d'un transport à routes strictes si une phase ultérieure est autorisée.

## Credentials historiques
pre_live_check_d6.py appelait AsyncSecureClient.create(private_key=...) sans credentials ni nonce explicites. Dans 0.11.0, nonce par défaut=0. Cela établit le nonce utilisé par le chemin de code inspecté, pas l'existence/validité actuelle du credential côté serveur ni l'identité de la clé privée historique.
Si le même signataire et le nonce 0 correspondent encore à un jeu existant, le GET de dérivation est la voie documentée pour restituer les trois champs sans connaître préalablement secret/passphrase. Il reste conditionné à une preuve L1 du signataire. La liste des API keys ne remplace pas cette preuve: elle requiert déjà L2 et ne livre pas les secrets. Aucun endpoint de récupération par API key seule trouvé. Aucune interface web de réaffichage du secret CLOB attestée par les sources consultées; les menus Builder/Relayer ne doivent pas être confondus avec CLOB L2.

## Phase minimale ultérieure — documentée, non exécutée
1. Autorisation distincte d'une récupération L1; identité du signataire historique et nonce 0 vérifiés, sans exploration de nonces ou de wallets. Conserver les deux flags false et les verrous monétaires.
2. Préparer un processus local isolé, sans constructeur sécurisé, sans relayer/RPC, sans POST/DELETE, sans redirection. Routes uniquement GET /time puis GET /auth/derive-api-key. Signataire local protégé; aucune clé en argument de commande, log, rapport ou conversation.
3. Produire uniquement une signature EIP-712 ClobAuthDomain version 1, chainId 137, type ClobAuth, address, timestamp, nonce. Elle prouve le contrôle du signataire: ce n'est ni une signature d'ordre ni une transaction, mais c'est une opération sensible distincte à autoriser.
4. Faire un seul GET de dérivation pour ce signataire/nonce. Validation stricte du triplet non vide. Échec/absence/ambiguïté => arrêt; aucun create_or_derive et aucun fallback POST.
5. Si récupération réussie, conserver une fois le triplet dans un stockage local protégé et hors Git, accessible seulement à l'utilisateur/service prévu. Ne pas écraser d'existant; ne pas inscrire le secret dans le rapport. Persister séparément signataire, nonce et environnement; wallet et signature type doivent être vérifiés pour les lectures de balance.
6. Revenir à la façade GET HMAC avec les seuls credentials L2 connus pour qualifier le compte. complete=false tant que l'exhaustivité distante n'est pas prouvée.
7. Si aucun credential n'existe, une NOUVELLE autorisation de création serait nécessaire: un POST /auth/api-key avec L1 pour un nonce explicitement choisi, puis stockage protégé. Ce n'est plus une phase strictement non mutante; aucun POST ne fait partie du présent travail.

Le préfixe local READONLY ne confère aucun scope read-only au credential côté serveur. La frontière de lecture est imposée par notre transport; les permissions effectives du credential restent à établir.

## Sources
- Documentation officielle: https://docs.polymarket.com/getting-started/api (L1/L2, nonce, derive/create et triplet complet).
- Documentation officielle: https://docs.polymarket.com/trading/wallets-auth (réponses Create/Derive, distinction compte/relayer).
- SDK installé: polymarket/_internal/actions/auth.py lignes 31,67,72,77,88; clients/async_secure.py lignes 750,2253,2881,3858,3966; models/clob/api_key.py ApiKeyCreds; _internal/l1_auth.py build_api_key_auth_typed_data et sign_api_key_auth.
- Projet: analysis/pre_live_check_d6.py _client_factory et get_balance_allowance.
