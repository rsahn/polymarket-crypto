# Qualification manuelle du L2 existant

Depuis la racine du dépôt sur la machine cible :

    python -B .\analysis\qualify_stored_l2.py --network --target-machine

Lecture exclusive du fichier DPAPI existant ; contrôle ACL, enveloppe signer/nonce/production et triplet. Aucun .env ni clé privée chargés. Aucun code de récupération importé, aucun credential créé/modifié. Uniquement HMAC des GET. Wallet historique confirmé, classification SDK locale sans règle universelle signer=wallet.

Ordre : /time public, /balance-allowance, /data/orders paginé, /data/trades paginé, /v2/positions paginé, état local. Chaque étape a timestamps, statut et erreur fixe. Une erreur authentifiée ne cache pas les autres étapes indépendantes ; aucun retry/fallback, aucun changement d'identité. Preflight time en échec => aucun GET authentifié. Indexeur public indépendant.

Montants raw uniquement ; conversion bloquée tant que decimals et collateral du compte ne sont pas démontrés. Pagination complète d'une vue != exhaustivité globale. Balances conditionnelles bloquées tant que le type des actifs reste inconnu. complete=false, jamais d'armement.

État local : variable publique READONLY_EXECUTION_STATE_DB si une base autoritative existe. Lecture SQLite mode=ro, query_only, sans constructeur ExecutionStore/création/migration. Sinon LOCAL_STATE_NOT_CONFIGURED ; aucun choix automatique de DB historique ou de test. CLOSED local ne prouve pas la flatness distante. Comparaison globale bloquée sans couverture complète et balances conditionnelles.

Rapport exclusif horodaté AUTHENTICATED_READ_ONLY_<UTC>.json à la racine. Retourner seulement ce JSON. Aucun compte complet, order ID, champ L2, header ou HMAC. Les contrats publics sont autorisés comme provenance SDK. Erreurs fixes sans exceptions brutes. Le scan d'absence de fuite reste limité au périmètre indiqué.

Flags live false, transport monétaire hard-locked, BTC V1 inchangée. Aucune exécution réseau pendant cette préparation.
