# Sonde manuelle locale read-only

Depuis la racine C:\Users\Ramy\Documents\polymarket-crypto, dans le PowerShell normal de la machine cible:

```powershell
python -B .\analysis\qualify_local_readonly.py
```

Retourner uniquement READINESS_LOCAL_NETWORK.json, créé à la racine. Ne pas retourner .env, credentials, terminal brut, clés ou signatures. Le fichier contient seulement les résultats normalisés, compteurs, horodatages, routes sans paramètres ni headers, et motifs de blocage. Il peut contenir des montants de collateral utiles au contrôle des unités, mais aucune adresse de compte ou ID d'ordre. Les adresses de contrats publics et les slugs BTC sont des métadonnées.

Python utilisé: l'installation contenant polymarket-client 0.11.0. Une version différente ou absente bloque la sonde sans accès réseau. Aucun package installé automatiquement. Ne pas utiliser l'ancien qualify_readonly_network.py pour cette exécution.

Les deux flags doivent rester false dans .env ET le processus; un conflit bloque avant toute lecture. Aucun fichier .env n'est modifié. Aucun transport raccordé au runner, aucun signal BTC V1 modifié. Le rapport existant n'est jamais écrasé: le conserver/renommer avant une nouvelle exécution.

## Lectures publiques
CLOB /time, geoblock, Gamma marché BTC 5m courant et deux GET /book; Data API /v2/positions pour POLYMARKET_WALLET_ADDRESS si cette adresse attendue est présente. Les erreurs de l'une des sources ne bloquent pas les autres lectures indépendantes. Le geoblock est expurgé de l'IP et de la localisation. Les snapshots REST ne démontrent pas la continuité d'un flux synchronisé.

Les succès HTTP 200 de la machine cible rapportés par l'utilisateur ne remplacent pas les mesures de cette sonde. Les anciens HTTP 403 Codex restent limités à cet environnement.

## Lectures authentifiées facultatives
Uniquement avec des credentials L2 DEJA EXISTANTS et une identité explicitement configurée, dans .env ou le processus local:
- READONLY_CLOB_API_KEY
- READONLY_CLOB_API_SECRET
- READONLY_CLOB_API_PASSPHRASE
- READONLY_SIGNER_ADDRESS
- READONLY_SIGNATURE_TYPE (0 EOA, 1 proxy, 2 safe, 3 deposit wallet; doit correspondre à la classification déterministe du SDK)
- POLYMARKET_WALLET_ADDRESS (wallet attendu, jamais remplacé silencieusement)

Ne jamais transmettre ces valeurs dans la conversation. Si elles sont absentes, laisser les contrôles BLOCKED: ne pas créer de credentials pour cette sonde. Elle ignore les clés privées et les credentials relayer. Elle ne dérive aucune clé, ne signe aucun message EVM, aucun ordre, aucune transaction. Seul le HMAC d'authentification HTTP GET peut être calculé en mémoire à partir du secret L2 existant. Aucun SDK SecureClient.create/_create/bootstrap utilisé.

GET authentifiés autorisés: /balance-allowance, /data/orders, /data/trades. Pas de POST, DELETE, update allowance, annulation, déploiement, RPC ou fallback de création. Identité non classifiable (notamment session key non démontrée) => BLOCKED. La classification locale n'atteste pas une permission globale distante.

## Limites volontairement bloquantes
Le collateral est identifié comme CONFIG_ONLY par la configuration SDK; symboles/décimales de documentation distingués des lectures on-chain (non réalisées). Les montants COLLATERAL ne sont pas renommés USDC. Les types d'actifs conditionnels inconnus empêchent leur comparaison authentifiée. La pagination peut être complète pour une vue sans prouver tous les actifs/ordres du wallet. complete reste false. Le journal de risque réel, la réconciliation globale et la synchronisation du carnet restent nécessaires. La sonde ne permet jamais l'armement.

## Validation hors réseau
Tests ciblés: backend/tests/test_local_network_probe.py. Parcours avec et sans credentials simulés, erreurs, version SDK, flags contradictoires, secrets expurgés, interdiction du constructeur et protection contre écrasement. Les tests utilisent un transport factice; aucune nouvelle sonde réseau n'a été exécutée depuis Codex.


## Diagnostic public uniquement
`python -B .\analysis\qualify_local_readonly.py --public-only`

Ce mode ne lit pas .env et ne charge aucun credential ni wallet. Il lit uniquement les deux flags du processus pour rejeter un armement existant; .env reste intact. Exactement trois routes possibles: CLOB /time, geoblock /api/geoblock et Gamma /markets?limit=1. Aucun carnet, Data API, bootstrap ou compte authentifié. Sortie exclusive horodatée READINESS_LOCAL_NETWORK_PUBLIC_<date_UTC>_<heure_microsecondes>.json; ancien rapport conservé. Retourner uniquement ce nouveau JSON.

Le transport ajoute explicitement User-Agent: Mozilla/5.0 comme la requête manuelle réussie. Aucune modification de proxy/VPN/environnement et aucun essai réseau Codex. Accept: application/json conservé; redirects toujours rejetés.
