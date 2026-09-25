# READ_ONLY_ADAPTERS_VALIDATED_NOT_READY_FOR_LIVE

## Validation du 25 septembre 2026
315 passed, 0 failed, 0 errors; 25 subtests passed, 3 warnings.
Audit statique: 83 fichiers, frontière monétaire isolée, trois méthodes verrouillées dès leur première instruction.
Harnais: 16 méthodes SDK monétaires interceptées, zéro appel; trois tests du verrou transport, zéro connexion externe. Les doublures simulent les réponses uniquement.
REAL_ORDERS_ENABLED=false et LIVE_EXECUTION_ARMED=false dans .env (lecture sélective FLAGS.json) et dans le processus de test. Aucun client authentifié créé, aucune lecture du compte réel effectuée.
BTC V1 analysis/d6/paper_live.py identique à 4cb928c; aucun changement du collecteur ou du signal. Aucun transport raccordé au runner.

## Capacités SDK inspectées
polymarket-client 0.11.0 installé dans Python 3.13. SDK_CAPABILITIES.json contient les signatures intégrales, modèles, sources et SHA256.
- get_balance_allowance(*, asset_type, asset_id=None, token_id=None) -> BalanceAllowance: GET authentifié /balance-allowance, balance et allowances entiers en unités de base. Division Decimal par 1e6, spender exact obligatoire.
- get_order(*, order_id) -> OpenOrder: GET authentifié /data/order/{id}; absence/inaccessibilité ne prouve jamais la clôture.
- list_open_orders(*, asset_id=None, token_id=None, id=None, market=None) -> AsyncPaginator[OpenOrder]: GET authentifié /data/orders.
- list_account_trades(*, asset_id=None, token_id=None, id=None, market=None, maker_address=None, after=None, before=None) -> AsyncPaginator[ClobTrade]: GET authentifié /data/trades.
- list_positions(*, user=None, ..., full_history=False, page_size=100) -> AsyncPaginator[Position]: Data API publique par wallet, disponible sur le client sécurisé; pas une preuve authentifiée exhaustive d'inventaire.
Pagination bornée, curseurs cycliques/troncature rejetés. PositionSource demande full_history, archives et seuil zéro, puis compare chaque actif connu à sa balance conditionnelle authentifiée.

## Invariants ajoutés
AccountStateSource: identité wallet, spender exact, unités explicites, données fraîches; jamais de réemploi d'un succès après erreur.
PositionSource: incohérence indexeur/balance, type d'actif inconnu ou inventaire omis => rejet.
BookStateSource: deux côtés synchronisés dans une génération monotone, déconnexion invalide tout, profondeur triée valide, fraîcheur 500 ms.
GeoBlockSource: réponse booléenne explicite requise, TTL 60 s, erreur => indisponible.
SessionRiskSource: journal REAL_CONFIRMED réconcilié, frais complets, cash moins réservations, PnL net et positions réels fournis par le journal. Aucun PnL initial fictif.
Sortie: seulement après la décision V1 existante; quantité <= détenu confirmé, prix limite dérivé des bids et arrondi au tick, slippage explicite 0..100 bps. Liquidité partielle => reliquat positif; manque de liquidité => EXIT_REQUIRED. Un plan ne peut jamais déclarer CLOSED. Les tests existants du contrôleur vérifient la récupération après sortie partielle et le refus de nouvelle entrée.
ProductionReadinessCheck rassemble les douze contrôles, conserve leurs observations et interdit toute soumission. READINESS_UNBOUND.json est un rapport réel de configuration non raccordée, pas un test du compte réel.

## Limites bloquantes, sans hypothèse locale
1. Les ordres/trades sont limités à la visibilité des credentials. Les session keys ne constituent pas une vue de tout le wallet. AccountStateSource.complete reste false; preuve d'exhaustivité distante à définir avant armement.
2. Inventaire paginé indexé non atomique: la concordance par actifs connus ne prouve pas l'absence de tout autre actif. PositionSource.complete reste false.
3. COLLATERAL ne signifie pas automatiquement USDC. La documentation actuelle décrit pUSD; symbole USDC non présumé, champs USDC absents sans configuration vérifiée. Vérification d'identité du contrat collateral requise.
4. Sources non raccordées aux flux persistés de production: client de lecture sans effet secondaire, alimentation du carnet, journal réel frais/PnL et réconciliation distante exhaustive restent à intégrer. Les adaptateurs sont validés sur fixtures et modèles SDK; pas de qualification réseau réelle. Le contrôleur expérimental et le runner restent non raccordés à ces adaptateurs et au transport monétaire.
5. AsyncSecureClient.create appelle _ensure_wallet_ready et peut déployer le deposit wallet. Il n'est jamais appelé par cette phase. Un chemin d'initialisation exclusivement lecture reste à établir.
6. Le plan de sortie reste une fonction pure testée, non branchée sur le runner. Le signal BTC V1 est intact.

Références officielles consultées:
- https://docs.polymarket.com/trading/manage-orders (portée des session keys et APIs)
- https://docs.polymarket.com/concepts/pusd (collateral)
- https://data-api.polymarket.com/v2/docs (pagination indexée)
Aucune API supposée ou endpoint inventé pour contourner ces limites.

## Test historique Phase A
Le commit initial 7cb0198 contient déjà app/collectors/binance.py et app/storage/db.py, pas les modules importés par l'ancien test. Contrat de test historique obsolète, aucun contrat de production récemment supprimé. Original conservé dans LEGACY_PHASE_A.txt. Deux tests migrés: schéma actuel puis bookTicker enrichissant aggTrade stocké, websocket simulé, DB temporaire. Aucun skip.

## Preuves reproductibles
RED.log: dix échecs avant création des modules. HARDENING_RED.log: trois défauts reproduits, 17 succès. HARDENING_GREEN.log: 20 succès après corrections minimales.
FULL_TESTS.log: suite maximale précédemment collectable, désormais sans erreur de collecte.
Commande: python -B analysis/validate_execution.py backend/tests tests analysis/d5/auditor_next analysis/d51/test_review51.py analysis/d51/latency_tools/test_diagnose.py analysis/d6/tests analysis/d6/pipeline analysis/d6/research analysis/d6/paper_runtime analysis/test_c3_d4_analysis.py --continue-on-collection-errors
Audit: python -B analysis/audit_live_boundary.py
Rapport sans bindings: python -B analysis/check_production_readiness.py
Les logs restent locaux; MANIFEST.json en conserve les empreintes.
