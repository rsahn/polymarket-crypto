# REAL_NETWORK_READ_ONLY_QUALIFICATION — BLOCKED_NOT_READY

## Résultat
Trois GET réellement tentés le 25 septembre 2026 depuis cet environnement: geoblock, /time CLOB, découverte /markets Gamma. Chacun retourne HTTP 403. Aucun contournement, changement de proxy, autre origine de compte ou nouvel essai d'authentification après le refus.
La cause précise du 403 (edge, politique réseau, restriction régionale ou autre) n'est pas démontrée. Un HTTP 403 geoblock ne signifie PAS blocked=true ou false.
READINESS_NETWORK.json contient les douze contrôles, leur provenance et le journal expurgé. Deux contrôles locaux PASS (flags et verrou); dix contrôles bloqués. complete=false, ready_for_arm=false, submit_allowed=false.

## Collateral: provenance distincte par niveau
- Asset type: COLLATERAL, enum et constructeur de requête installés polymarket-client 0.11.0.
- Environnement inspecté: PRODUCTION_CONFIG, Polygon chain_id 137, CLOB https://clob.polymarket.com.
- Contrat configuré: 0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB.
- Adresse corroborée par https://docs.polymarket.com/resources/contracts (consulté le 25 septembre).
- Symbole documenté pUSD, decimals documentés 6: https://docs.polymarket.com/concepts/pusd.
- Symbole/decimals lus directement on-chain: NON. Liaison de la balance effective du compte à ce contrat: NON, authentification non atteinte. Ne pas présenter cette identification de configuration comme preuve du compte réel. Aucun renommage automatique en USDC.

## Inspection SDK et client GET
AsyncSecureClient.create -> _create -> _bootstrap_credentials peut appeler create_or_derive_api_key qui tente un POST /auth/api-key avant le GET de dérivation. create appelle ensuite _ensure_wallet_ready, potentiellement déploiement et approbations. Même des credentials fournis ne rendent pas create sûr. Ni ce constructeur ni ses variantes privées ne sont appelés.
ReadOnlyClient est une façade minimale sans signataire, construction de wallet ou méthodes monétaires. Elle réutilise seulement les constructeurs de requêtes et parsers inspectés de la version 0.11.0. GetOnlyTransport expose seulement get_json, route exacte autorisée, HTTPS, aucun redirect, réponse bornée à 4 Mo et timeout 8 secondes. Les credentials ne sont transmis qu'au domaine CLOB configuré. Les logs omettent query strings, headers, réponses brutes, adresses du compte et erreurs textuelles.
La sonde préparée prévoit un ClobAuthDomain local pour GET /auth/derive-api-key, jamais une signature d'ordre. Ce chemin n'a PAS été atteint: /time a été refusé avant toute signature. Aucun POST de création de clé en fallback. Wallet: uniquement dérivation locale puis vérification GET /deployed d'un wallet existant selon l'ordre UUPS/beacon inspecté; aucun déploiement si absent. Ce chemin n'a pas été atteint non plus.
get_order requiert l'autorisation d'une route exacte pour un ID connu; aucun ID n'a été disponible ni aucune lecture d'ordre tentée.

## Sources: démontré / non démontré
AccountStateSource: pas de balance ni allowance réseau, pas de wallet authentifié, pas d'ordres ou trades lus. Modèles/signatures disponibles et tests hors ligne ne prouvent pas le compte réel.
PositionSource: pas de Data API ni balance conditionnelle lues. Comparaison d'unités et identity wallet testée hors ligne seulement.
BookStateSource: Gamma refusé; aucun asset ID ni timestamp de carnet réellement reçu. Le qualificateur REST contrôle deux snapshots, identité market/token, profondeurs et âge source, mais refuse de convertir des snapshots REST en flux synchronisé. Une observation GET ponctuelle ne qualifie pas la continuité websocket.
GeoBlockSource: 403 réellement observé, JSON non obtenu; état géographique indéterminé.
Pagination/cursor: non exercés sur le réseau; bornes et rejet de boucle testés hors ligne. Aucun compte vide ne peut être inféré.

## Exhaustivité et architecture proposée
La documentation officielle https://docs.polymarket.com/trading/manage-orders limite la visibilité des session keys à leurs propres ordres/trades. Les méthodes list_open_orders/list_account_trades ne certifient pas tous les ordres du wallet. Aucun endpoint global certifiant cette exhaustivité n'a été démontré. Ne pas remplacer cette preuve par une liste locale de credentials ou par l'absence de résultat.
Architecture fail-closed: conserver un registre distant vérifiable des autorités/credentials et de leurs scopes, agréger chaque vue paginée avec watermark/identité, surveiller les changements d'autorisation; tant que ce registre et une vue globale ne sont pas démontrés, complete=false. Un wallet dédié réduit les interactions mais ne constitue pas à lui seul une preuve d'exhaustivité.
Inventaire: agréger les actifs de l'indexeur, des ordres, trades, journal et historique de transferts ERC1155 à un bloc finalisé; comparer chaque actif aux balances conditionnelles du type explicitement établi. Toute différence, actif inconnu, curseur tronqué, wallet divergent ou retard indexeur -> RECOVERY_REQUIRED, aucune entrée. Les balances des seuls actifs connus ne détectent pas tous les orphelins; il faut une source exhaustive d'événements avec checkpoint et contrôle des réorganisations. Les protocoles V1/V2 et combos doivent être couverts sans déduire le type d'un actif arbitraire. Tant que ce mécanisme n'est pas qualifié, complete=false.
Aucun de ces composants supplémentaires n'est présenté comme implémenté ou qualifié sur le compte.

## Validation et sécurité
9 nouveaux cas: routes GET, absence de mutations, redirects, snapshots non synchronisés, asset invalide, confidentialité des erreurs, bases HTTPS invalides. RED: 5 échecs avant implémentation; GREEN: 5 succès puis 4 cas supplémentaires dans la suite complète.
Suite maximale: 324 passed, 0 failed, 0 errors; 25 subtests passed, 3 warnings. Harnais: zéro appel SDK monétaire, 16 méthodes interceptées, trois tests du verrou et zéro connexion externe pendant pytest.
Audit statique: 85 fichiers PASS. Trois méthodes monétaires restent hard-locked. Flags .env et processus vérifiés false avant les GET. BTC V1 analysis/d6/paper_live.py identique à 4cb928c. Aucun transport monétaire raccordé.
La preuve réseau est le journal des trois GET et l'arrêt avant signature; les compteurs de sécurité décrivent ce chemin exécuté, pas une attestation externe de tout le SDK.

## Blocage à lever
Rétablir ou expliquer l'accès autorisé aux trois endpoints officiels depuis cet environnement. Sans réponse réseau exploitable, impossible de qualifier authentification, inventaire, pagination, unités du compte et fraîcheur. Aucun feu vert réel demandé ni aucun armement possible. Les limites d'exhaustivité resteront bloquantes même après résolution des 403.
