# Processus local isolé — EXISTING L2, non exécuté

Le signataire attendu est fixé à l'adresse publique déjà validée, production Polygon 137, nonce 0. L'ancien CLI preview reste disponible; le nouvel outil dédié est analysis/recover_existing_l2_local.py, sans import par D6 ou par qualify_local_readonly.py.

## Procédure autorisée à ce stade : preview et validation locale seulement
Depuis la racine du dépôt dans PowerShell :

    python -B .\analysis\recover_existing_l2_local.py --preview --validate-storage

Ce mode n'ouvre pas .env, ne lit pas de clé privée, ne signe pas, ne fait aucun GET. Il valide DPAPI et la création/publication d'un credential entièrement fictif dans un dossier temporaire dédié à permissions restrictives, puis supprime uniquement cette fixture. Il laisse un rapport expurgé L2_RECOVERY_<horodatage>.json créé exclusivement à la racine. Un rapport existant n'est jamais écrasé. Retourner uniquement ce JSON, jamais .env, fichiers DPAPI, credentials ou signatures.

Le stockage réel prévu est %LOCALAPPDATA%\PolymarketD6L2\credential.dpapi, hors Git. Il n'est pas créé par le preview/validation. Tout dossier de destination déjà existant bloque avant réseau, même vide. Pas de suppression automatique de données existantes.

## Chemin d'exécution livré mais NON exécuté
Le mode de récupération séparé exige un terminal interactif et une phrase de confirmation exacte APRÈS affichage du preview. Aucune option de confirmation automatique. L'utilisateur n'a pas encore décidé d'exécuter ce mode. Ne pas l'utiliser avant cette décision séparée.

Séquence: confirmation, contrôles flags, création exclusive du dossier privé, GET /time (timestamp entier frais à 5 secondes), puis lecture tardive de SIGNER_PRIVATE_KEY dans le .env existant du dépôt, contrôle adresse dérivée contre le signataire fixé, signature EIP-712 ClobAuth uniquement, au maximum un GET /auth/derive-api-key. Aucun constructeur SecureClient ni chemin de création. Aucun retry; chaque erreur consomme la tentative. Aucun nonce/signer/endpoint configurable. POST/DELETE/redirects, relayer, wallet bootstrap, annulation, allowance update, ordres et transactions absents.

Réponse: objet JSON exact apiKey/secret/passphrase, trois chaînes ASCII imprimables non vides, sans espaces/contrôles, taille bornée; clés supplémentaires/dupliquées, types incorrects, JSON invalide et HTTP différent de 200 refusés. Le SDK 0.11.0 expose ces champs comme strings; aucun format UUID ou longueur de secret non démontré n'est supposé.

## Stockage et erreurs
DACL Windows protégée, une seule ACE pour le SID de l'utilisateur courant, droits hérités par fichiers; DPAPI CurrentUser avec UI interdite. Le contenu en clair n'est jamais écrit. Un fichier de staging contient uniquement le blob chiffré; flush/fsync puis MoveFileExW sur le même volume, sans remplacement ni copie, publication atomique. Le fichier final n'apparaît qu'après l'écriture chiffrée complète.

Timeout/réponse invalide => aucun staging ni credential. Échec d'écriture/publication => nettoyage du staging chiffré et du dossier créé par cette tentative. Une interruption brutale du processus/OS peut laisser un staging chiffré; cela ne constitue pas un credential final et la tentative suivante est bloquée par le dossier existant. Pas de reprise automatique. Un échec de rapport après publication peut laisser un credential valide: rapport d'échec n'autorise jamais une nouvelle tentative automatique.

Les exceptions sont remplacées par des codes fixes; ni traceback, réponse brute, headers, signature ni credential dans le rapport/stdout. Le rapport indique seulement paramètres publics, booléens et motifs fixes. Python ne garantit pas l'effacement immédiat de toutes les copies de secrets en mémoire; DPAPI protège le stockage, pas un processus compromis ni un administrateur local.

## Tests et portée
Tests réseau via fakes, signature via faux Account, contenu local entièrement fictif. DPAPI réel Windows testé sur fixture (chiffrement/déchiffrement), ACL inspectée directement via .NET, refus de remplacement et interruption vérifiés. Aucun ClobAuth réel signé et aucun credential réel récupéré. Le SDK monétaire et les connexions externes sont bloqués par validate_execution.py.

REAL_ORDERS_ENABLED=false, LIVE_EXECUTION_ARMED=false, transport monétaire hard-locked, BTC V1 inchangée. L'intégration de lecture ultérieure du stockage DPAPI dans les adaptateurs authentifiés reste une phase distincte; aucun raccordement au runner.
