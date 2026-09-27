# BTC V1 prospective protocol — depth, fee and capacity qualification

**BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED**

Baseline HEAD `333877dfad58269806b6623dbb130f4a24dc9d33`, branche `d6-live-execution-staging` ; 983 tests / 79 sous-tests. BTC V1 et les conventions économiques restent inchangées. Cette livraison ajoute un audit historique, un lecteur de journal incrémental non adopté et dix tests. Elle ne choisit aucun modèle selon le PnL.

| # | Élément demandé | Résultat |
|---|---|---|
| 1 | DEPTH_REUSE_EMPIRICAL_AUDIT | 15 signaux historiques uniques ; 0 book d'entrée réellement identifié ; 15 cas C. Counts/rates de reuse, overlap et updates entre entrées = UNKNOWN, jamais zéro imputé. [Données par opportunité](DEPTH_REUSE_EMPIRICAL_AUDIT.json). |
| 2 | Classification depth | DEPTH_MODEL_NOT_IDENTIFIABLE_FROM_CURRENT_EVIDENCE. [Preuve et limites](DEPTH_SEMANTICS.md). |
| 3 | Impact des modèles | Opportunités/fills affectés, différence de quantité et PnL : non calculables sur les 15 cas faute de books/clocks effectifs. Modèle C non admissiblement démontré, non évalué. Contre-exemple synthétique A=100 vs B=50 shares déjà scellé, pas fréquence empirique. |
| 4 | Observability R1 | Version inchangée et NON ADOPTÉE ; AST ceaa1974edd442eedb94c038940cdcd0a8e987139b58a55316a8cc855680d6ef. Les observations supplémentaires ne prouvent pas une disponibilité contrefactuelle de liquidité. |
| 5 | Real V1 binding | REAL_V1_BINDING_BLOCKED_BY_UNIDENTIFIED_DEPTH_SEMANTICS |
| 6 | Fee rounding | UNSPECIFIED pour le chemin de match applicable ; arrondis du montant client distincts. |
| 7 | Fee aggregation | UNSPECIFIED pour ce marché. Le module officiel reçoit des montants de l'opérateur ; ce n'est pas sa règle d'agrégation. |
| 8 | Partial-fill fees | Allocation / nombre d'arrondis inconnus pour le marché. |
| 9 | Qualification / borne conservative | MARKET_FEE_UNQUALIFIED. Pas de FEE_CONSERVATIVE_UPPER_BOUND_PROVEN applicable ; preuve conditionnelle et contre-exemple ci-dessous. |
| 10 | JOURNAL_168H_UPPER_BOUND | UNKNOWN. Schéma sans maximum de bytes/event ou nombre d'événements économiques/opportunité. Borne conditionnelle signaux seulement : 604800. |
| 11 | CHECKPOINT_168H_UPPER_BOUND | CHECKPOINT_CAPACITY_UNPROVEN : schéma, cadence, taille et nombre non définis pour checkpoints économiques. |
| 12 | Architecture replay | Nouvelle entrée streaming et index exact des IDs sur disque ; transition économique existante inchangée. Historique économique encore O(N). [État nécessaire](REPLAY_ARCHITECTURE.md). |
| 13 | Équivalence | PASS canonique aux préfixes avec position ouverte, sortie partielle/résiduel et clôture ; duplicate/torn/hash/partition rejetés. PASS sur le journal synthétique existant de 5001 événements. |
| 14 | Mémoire / performance | Nouveau lecteur : 0.536775 s ; 9316.760 events/s ; 5158394.232 bytes/s ; pic RSS 34873344 bytes ; index disque 110592 bytes. 5001 lignes comptables retenues. Pas extrapolation semaine. [Mesure](STREAMING_REPLAY_MEASUREMENT.json). |
| 15 | QUALIFIED_REQUIRED_SPACE | UNKNOWN ; archive 168h acquise = 153994953187 bytes ; réserve minimale acquise = 369587887649 bytes. Journal/checkpoints inconnus ne valent pas zéro. |
| 16 | Espace libre mesuré | 47030665216 bytes au 2026-09-27T00:57:41.773466+00:00. |
| 17 | Additional bytes required | Total exact UNKNOWN ; déficit minimal 322557222433 bytes. Pas STORAGE_SPACE_ONLY_BLOCKER car les bornes et le replay restent non qualifiés. [Calcul](CAPACITY_BOUNDS.json). |
| 18 | Tests ciblés | 13 PASS / 23 sous-tests / 0 FAIL. Un premier nouveau test attendait une liste au lieu du tuple réel : attente corrigée, production inchangée. [Log final](TARGETED.log). |
| 19 | Full suite | 993 PASS / 88 sous-tests / 0 FAIL à la revérification sans changement. Premier passage : 3 échecs de tests temporels existants / 990 PASS / 88 sous-tests ; leurs 4 tests passent isolément. Tous les logs sont conservés, aucune modification de délai. [Final](FULL_SUITE_RECHECK.log), [premier passage](FULL_SUITE.log), [isolé](TIMING_RECHECK.log). |
| 20 | Audit / leak scan | PASS du périmètre ; contrôle des sources testées, anciennes preuves et empreintes protégées. Pas une qualification économique. [Audit](AUDIT.json). |
| 21 | BTC V1 | Deux hashes inchangés, valeurs ci-dessous. |
| 22 | Criteria | 869a386b9112a572247e3fb61ffbf4a27afb20493a791929e72f52bc0d9cd06a inchangé ; 72/48/48h, embargo60s inchangés. |
| 23 | D6 | Aucun composant modifié ; Genesis inchangée ; SYSTEM_READY=false ; current_inventory_proven=false. |
| 24 | Flags | REAL_ORDERS_ENABLED=false ; LIVE_EXECUTION_ARMED=false ; submit_allowed=false. |
| 25 | SDK | 0 tentative monétaire, 16 méthodes gardées et 0 tentative de connexion externe pendant les tests ; aucun ordre/cancel/signature/transaction/allowance update. |
| 26 | Commit | Commit séparé après les contrôles, SHA exact dans la réponse de livraison. Aucun artefact préexistant inclus. |
| 27 | Push | PUSH_PENDING_AUTHORIZATION ; aucun nouvel essai. La précédente approbation automatique a refusé la publication publique sans autorisation spécifique. |
| 28 | Verdict | BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED |
| 29 | Blockers restants | Sémantique depth/binding ; frais exacts ou borne applicable ; bornes journal/checkpoint, replay économique borné et espace. Aucun autre chantier D6 ouvert. |
| 30 | Commande de collecte | Aucune : pas READY. Aucun TRAIN/VALIDATION/OOS/PAPER économique ou micro-live exécuté. |

## Ce que montrent réellement les books

Préfixe fixé de 1000 enveloppes BOOK de la capture technique existante : 2000 côtés, 95 réémissions d'état de token identique, 482 transitions de profondeur identique, aucune séquence exchange dans ces 2000 côtés. Ces nombres décrivent les observations, pas les opportunités économiques. [Preuve détaillée](PIPELINE_OBSERVATIONS.json).

Un price_change remplace la quantité au prix concerné ; il ne l'ajoute pas. La réémission du côté opposé conserve son état. L'event_id local, le hash d'enveloppe et le hash d'état de token ne sont pas interchangeables. Aucune de ces identités ne dit quels ordres externes auraient survécu à nos fills simulés. Le contrat actuel reste une convention conservatrice, non une sémantique empirique prouvée. Aucun reset de profondeur n'est adopté.

## Frais : recherche limitée aux inconnues

[SDK installé et classification par propriété](FEE_REMAINING_PROPERTIES.json). Le helper `adjust_buy_amount_for_fees`, lignes409–422, provisionne le pouvoir d'achat sans produire les frais de chaque match. Les arrondis d'order amount sont CLIENT_DEFINED ; cela n'établit pas l'arrondi du règlement.

Le [FeeModule officiel](https://raw.githubusercontent.com/Polymarket/exchange-fee-module/main/src/FeeModule.sol) prend les montants de frais fournis par l'opérateur et calcule des remboursements autour des matches. La formule de choix de ces montants n'y est pas établie. Son déploiement applicable au marché4961058 n'a pas été prouvé.

Le [CalculatorHelper officiel historique](https://raw.githubusercontent.com/Polymarket/ctf-exchange/main/src/exchange/libraries/CalculatorHelper.sol) utilise des divisions entières et une courbe basée sur min(p,1-p), avec unités dépendant du côté. Ce n'est pas une preuve du chemin effectif du marché dont la schedule publiée utilise p(1-p). Aucun code lu n'a été appelé pour signer ou envoyer quoi que ce soit.

Borne seulement conditionnelle : si chaque frais de match est au plus son calcul brut + u=0.00001, alors F_total <= somme(F_brut)+N*u pour N matches. Or le regroupement, N et l'application de cette hypothèse au règlement du marché ne sont pas établis. Deux matches de .002 shares à .5 et taux.07 peuvent donner .00008 avec HALF_UP séparé, contre .00007 pour le plafond du total brut. Ce contre-exemple est un test mathématique, pas un choix d'arrondi réel. Il interdit d'étiqueter le simple plafond agrégé comme borne universelle. Sans borne applicable, estimated_net_pnl<=actual_net_pnl n'est pas prouvé.

## Bornes : pourquoi les inconnues persistent

Le cooldown1000ms donne au plus604800 signaux dans un intervalle demi-ouvert de168h, sous les conditions indiquées dans CAPACITY_BOUNDS.json. Il ne limite ni les champs JSON, ni les niveaux/fills par signal, ni les MARK. Le test accepte un champ supplémentaire de1MiB ; `FIELDS.issubset` et l'absence de limite montrent que ce n'est pas un maximum. La limite4MiB du codec d'archive ne devient pas silencieusement un contrat du journal.

Les checkpoints économiques n'ont pas de format/cadence implémenté dans ce harness ; leur coût ne peut être fixé à zéro. L'index d'IDs du nouveau lecteur est aussi du stockage de travail, pas un checkpoint économique qualifié. Formule conservée : ceil((2*archive + journal_bound + checkpoint_bound)*1.2). Faute de bornes, le total exact reste inconnu.

## Empreintes inchangées

- paper_live.py : 5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364
- run_d6_paper_live.py : a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405
- Genesis : 5365085da95cecb49fa4c922b890e9803ef223fdefef541505c2dc5a3de7814f

Les anciens smokes, benchmarks et audits n'ont pas été relancés. La seule nouvelle mesure de replay porte sur le nouveau lecteur appliqué au journal synthétique existant ; ce petit historique MARK n'est jamais extrapolé au journal économique hebdomadaire.
