# Préparation seulement — exécution bloquée

Le CLI expose uniquement --preview. Aucun transport réseau, loader de clé privée, signature ou stockage de credential n'est implémenté dans cette phase. L'automate RecoveryPolicy est une spécification exécutable hors réseau; ses tests ne prouvent pas une intégration future qui n'existe pas encore. Aucun triplet réel ne peut être reçu ou écrit par ce code.

Le signataire attendu doit être configuré explicitement via L2_RECOVERY_EXPECTED_SIGNER (adresse publique seulement). Pas de fallback wallet, pas de dérivation depuis SIGNER_PRIVATE_KEY, pas de scan. Preview actuel NOT_CONFIGURED; sortie CLI 2. Les deux flags du processus doivent être false; ils ne sont jamais modifiés. Aucun fichier .env lu par le preview.

Conditions impératives avant une éventuelle livraison d'exécution séparément autorisée:
- confirmation interactive distincte APRES affichage du preview, rattachée au signataire exact, production Polygon 137 et nonce 0; refus/EOF => arrêt;
- primitive de lecture tardive de la clé uniquement depuis le stockage local déjà existant au moment de signer; aucun argument CLI, log, rapport ou temporaire;
- signature uniquement ClobAuthDomain v1 / ClobAuth, chainId 137; interdiction de signature d'ordre/transaction;
- deux routes GET exactes /time puis une seule /auth/derive-api-key, redirects refusés, budget consommé avant émission, aucun retry même après timeout; toute nouvelle tentative exige une nouvelle autorisation explicite;
- interdiction de tous les constructeurs/bootstrap SDK et chemins de création/relayer/RPC/mutation;
- avant signature et réseau, préparer un stockage de destination hors repository/Git avec ACL Windows limitée à l'utilisateur/service prévu; création exclusive, refus si destination existante; chiffrement DPAPI CurrentUser du triplet et écriture directe dans le fichier final protégé, aucun temporaire en clair; pas d'affichage de la réponse ou des exceptions pouvant contenir une réponse;
- validation du stockage protégé et tests DPAPI/ACL/anti-écrasement avant toute activation du chemin d'exécution. Aucun stockage en clair .env ajouté par cette préparation.

L'absence actuelle de stockage et de confirmation interactive d'exécution est un verrou de livraison, pas une capacité revendiquée. BTC V1 et transport monétaire inchangés.
