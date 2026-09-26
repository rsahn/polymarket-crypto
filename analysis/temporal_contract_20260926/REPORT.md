# D6 — contrat temporel par domaine

Date : 26 septembre 2026. Branche : `d6-live-execution-staging`.
Base avant refonte : `e1f0682349aaac240761732296eb0cf2cfecb678`.

## Résultat et périmètre

Migration progressive implémentée et testée. Le réglage global 500/1300 ne pilote plus les gardes de production. Le carnet conserve 500 ms. Aucun nouveau seuil économique n'est choisi. `SYSTEM_READY=false`, `ready_for_arm=false`, `submit_allowed=false` tant que les propriétés nécessaires restent non calibrées ou non prouvées.

La migration conserve **des gardes transitoires indépendantes de 500 ms** pour le compte, les positions, la réconciliation, le risque, l'observation inventory et les preuves cash. Elles restent des hypothèses conservatrices, pas des SLA justifiés. Les retirer serait une autre modification des protections : cette phase ne les retire pas. Les diagnostics sémantiques et leurs raisons sont séparés des `legacy_checks`, `legacy_health_checks` et `legacy_blockers`. Les lecteurs peuvent encore rejeter une acquisition trop ancienne avant sa qualification sémantique. Ce travail n'est donc pas une calibration achevée ni la suppression de toute influence des gardes historiques.

## Ancien contrat

Le contexte `freshness_policy` sélectionnait 500 ou 1300 ms, réutilisé par carnet, compte, positions, génération, risque et contrôleur. `GENERATION_STALE_500MS` pouvait masquer des risques différents. Première règle carnet dans `4a8c998`, ensuite propagation au contrôleur et au compte. L'audit de provenance fourni par l'utilisateur ne démontre aucune exigence externe ni calibration économique du 500 ms. Le watchdog D5 `STALE_BOOK_RECONNECT` à 10 s puis 4 s est un mécanisme de transport distinct ; les critères de trous D5.1 et les fenêtres causales D6 ne constituent pas une justification de ce SLA.

## Nouveau contrat

| Domaine | Contrat sémantique / risque protégé | Politique et garde transitoire |
|---|---|---|
| Transport WS | Connexion et synchronisation sont distinctes de l'âge du carnet ; éviter un flux déconnecté ou incomplet. Aucune nouvelle limite de liveness inventée. | STRUCTURAL_INVARIANT ; ping/pong existants préservés |
| Book | Deux côtés identifiés, génération correcte, ordre causal, carnet non croisé, timestamp source non futur ; éviter prix/profondeur périmés. `BOOK_STALE` au-delà de 500 ms. | BOOK_MAX_AGE_MS=500 ; CONSERVATIVE_EXISTING_POLICY, calibration économique requise |
| Signal BTC | Provenance source/réception/décision distincte, signal disponible et valide. `SIGNAL_STALE` ou `SIGNAL_UNAVAILABLE`. | SIGNAL_MAX_AGE_MS=500 : garde du contrôleur conservée, indépendante du book ; non calibrée pour BTC V1 |
| Authentification | Réussite de la lecture authentifiée liée au compte attendu dans le lecteur existant ; ni une balance suffisante ni son âge ne prouvent l'identité. | STRUCTURAL_INVARIANT, protections de binding existantes conservées |
| Balance | Montant fini, bonne dénomination, collateral suffisant ; protéger contre collateral insuffisant / compte erroné. | UNCALIBRATED ; ACCOUNT_READ_GUARD_MS=500 retenu |
| Allowance | Autorisation lue, montant fini suffisant et bonne dénomination ; protéger contre autorisation révoquée ou mauvais spender. Le binding spender existant est conservé. | UNCALIBRATED ; garde compte 500 retenue |
| Orders / trades | Pagination et acquisition complètes, aucune commande inconnue, composants de même génération liés au ledger ; prévenir double exposition et fill non observé. La cohérence locale n'atteste pas l'atomicité distante. | UNCALIBRATED ; gardes compte/réconciliation 500 retenues ; OPEN_ORDER_STATE_UNCERTAIN |
| Positions | Acquisition complète, quantités cohérentes et scope plat, génération liée au ledger ; protéger contre position non réconciliée. | UNCALIBRATED ; POSITIONS_READ_GUARD_MS=500 ; POSITION_STATE_UNCERTAIN |
| Inventory | Couverture canonique historique et preuve actuelle sont deux propriétés différentes. | COMPLETENESS_UNPROVEN ; INVENTORY_UNPROVEN ; garde d'observation historique 500 conservée |
| Réconciliation compte | Orders/trades/positions cohérents, ledger durable et réconcilié, identité génération/hash vérifiée. | UNCALIBRATED ; RECONCILIATION_GUARD_MS=500 ; ACCOUNT_UNRECONCILED |
| Session risk | Ledger réconcilié, frais complets, exposition connue, aucune exécution non résolue, identité de génération et recovery valide. Un champ manquant bloque ; les sources historiques ne fournissent pas encore toutes ces attestations. | UNCALIBRATED ; SESSION_RISK_GUARD_MS=500 ; SESSION_RISK_UNRECONCILED |
| Recovery | Intégrité durable attestée, hash valide, état CLOSED ou Genesis réconcilié maintenant ; ne pas confondre ancienneté et corruption/incomplétude. | STRUCTURAL_INVARIANT ; RECOVERY_STATE_INVALID ; aucun nouveau timeout |
| Geoblock | Lecture disponible, non bloquée ; protections précédentes conservées. | Readiness 60000 ms, contrôleur 500 ms : distinction historique explicite, pas nouvelle calibration |

Les limites distinctes sont déclarées dans `backend/app/live/temporal_contract.py`. L'ancien contexte reste une API de compatibilité dépréciée sans consommateur de production. Le CLI refuse désormais `--freshness-ms` avant toute qualification. Aucun champ non calibré ne donne un feu vert : la validité descriptive d'une observation est séparée de `ready`.

## BTC V1 — horloges et contrat exact

`backend/app/collectors/binance.py` : source `aggTrade.E` → `MarketTick.event_ts_ms` ; réception UTC locale `time.time_ns() // 1_000_000` → `recv_ts_ms` (nanosecondes conservées).

`analysis/run_d6_paper_live.py:79–110` : la logique BTC V1 utilise le temps reçu pour la courbe, le lookback 250 ms, le cooldown 1000 ms et `record_signal.ts_ms`. Le mouvement minimal est 0,0005 (5 bps). Ce `ts_ms` est un **timestamp de réception**, pas une mesure indépendante du temps réel de décision. Cette logique ne pose pas un maximum d'âge source de 500 ms. La garde `signal_ms` du contrôleur vient du contrat D6 d'exécution : origine interne, calibration non démontrée. Lookback et cooldown ne sont pas des limites de fraîcheur.

Ne pas confondre avec `analysis/d6/paper_runtime/engine.py`, un autre moteur qui utilise `Limits.fresh_ms=1000` sur source/réception/disponibilité et un score différent. Aucun de ces moteurs n'est modifié ni lancé ici.

Hash BTC V1 conservé (`analysis/d6/paper_live.py`) : `5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364`.

## Définition de current_inventory_proven et obstacle restant

Pour attester l'inventaire courant à une décision, il faut pouvoir reconstruire toutes les variations pertinentes jusqu'à une frontière de complétude commune connue de cette décision : même compte et périmètre d'actifs, ledger initial vérifié, cursor vérifié, plages sans gap/overlap, fixed-C et hashes canoniques revérifiés, CTF catch-up complet, checkpoint cohérent, réconciliation des ordres/trades/fills/positions et de leurs réservations, aucune exécution non résolue, aucune variation ultérieure au scan laissée hors couverture.

Le code peut prouver `inventory_through_C_proven` pour les actifs identifiés et une acquisition bornée cohérente. Il ne dispose pas d'un **watermark de complétude post-C commun** aux observations on-chain et aux vues compte/indexer. Une réception HTTP récente ne démontre pas que l'indexer a vu un transfert à C+1. Deux mondes (aucun transfert / transfert non encore observé) peuvent produire les mêmes réponses. Ce contre-exemple reste testé.

Ainsi aucun âge (0, 500, 1300 ms ou davantage), ni un booléen injecté `current_inventory_proven=true`, ne résout la preuve. Le nouveau contrat retourne toujours INVENTORY_UNPROVEN jusqu'à l'existence d'un vérificateur de complétude supporté. L'algorithme fixed-C est identique AST à la base, hors import du budget indépendant ; ses vérifications cursor, canonicalité, catch-up, couverture et ordre d'acquisition restent présentes.

## Shadow calibration préparée, non exécutée sur le réseau

Option `--shadow-calibration --calibration-shares N`, uniquement en mode offline ou target-machine avec `--health-contract`. N sert au VWAP hypothétique, ne change aucun sizing d'ordre. Mémoire bornée, compteurs de pertes et erreurs, timestamps originaux préservés. L'instrumentation ne contient aucun appel réseau ni client d'ordres.

Pour la génération évaluée : book_age_ms, signal_age_ms, balance_age_ms, orders_age_ms, positions_age_ms, inventory_proof_age_ms. `inventory_proof_age_ms` est l'âge de l'observation historique, pas une certification actuelle. Les timestamps manquants restent null.

Par update de carnet accepté : bid/ask, spread, profondeur, intervalle reçu, mouvements, VWAP d'achat hypothétique et slippage relatif au meilleur ask, profondeur insuffisante explicite. Les observations sont isolées par marché/token/génération. `sample_stage=BOOK_PROCESSING_OBSERVATION` et `decision_is_execution=false` : le timestamp de traitement d'un update n'est pas une décision de trading. L'évaluation readiness fournit son propre instant distinct.

Le tap `ShadowCalibration.signal(...)` peut recevoir une vraie décision V1 et mesurer le book causal à cet instant ; le qualificateur actuel **ne lance pas BTC V1 et n'est pas branché sur ce flux**. Il rapporte donc `signal_status=NOT_OBSERVED`, signal_age_ms=null, plutôt que fabriquer une distribution. La connexion à un observateur V1 read-only et les preuves de son horodatage restent nécessaires pour la calibration complète.

Limites : seules les updates acceptées par le carnet strict sont instrumentées ; rejets comptés, profondeur rejetée non reconstruite. Cette sélection tronque la distribution et ne justifie aucun relâchement au-delà de 500 ms. Échantillon borné, une génération par qualification, pas un dataset statistique. Slippage théorique instantané sans frais, file d'attente ni latence d'exécution ; pas une mesure des fills réels. Aucun SLA sélectionné, aucun OOS utilisé. Une future calibration devra préenregistrer volumes/horizons, couvrir les rejets avec une capture indépendante et joindre les vraies décisions avant de conclure.

## Validation

- RED : `RED.log`, `CALIBRATION_RED.log` (modules absents avant implémentation).
- GREEN initial et intégration conservés ; 18 tests directs de domaines/calibration.
- Suite complète initiale : 10 anciennes attentes globales/ready échouaient, 804 réussissaient. Les assertions ont été migrées vers le contrat plus strict, sans suppression des tests de garde.
- Suite finale : **817 passed, 25 subtests passed**, 3 avertissements DuckDB préexistants (`FULL_FINAL.log`).
- Audit final : **AUDIT_OK**, 122 fichiers, appels monétaires isolés, trois méthodes submit/cancel verrouillées (`AUDIT_FINAL.log`).
- Harness : REAL_ORDERS_ENABLED=false, LIVE_EXECUTION_ARMED=false, sdk_monetary_attempts=0, 16 méthodes SDK gardées. Aucun ordre/cancel/transaction/update allowance ; aucune qualification réseau lancée dans cette phase.
- Tests : domains indépendants, account ancien/book frais, book stale/account descriptivement valide, positions/orders/risk incohérents, recovery manquant, identité ledger/génération, inventory impossible à rendre current par timeout, global 1300 inopérant, hook réel StreamBook avec rejeu synthétique, lifecycle du CLI shadow et refus du mode potentiellement écrivant Genesis.

## Fichiers préexistants et intégrité

`BASELINE.json` consigne l'état Git initial et 224 hashes de fichiers préexistants lisibles. `INTEGRITY_FINAL.json` : 222 identiques ; deux télémétries D5 (`analysis/d5/resumed_review_20260920_214402/telemetry.json` et `.jsonl`) ont évolué pendant cette phase sans écriture de notre part. Elles sont exclues du commit ; aucune restauration ni arrêt du processus producteur tenté. On ne prétend pas que leurs hashes sont restés fixes.

Les autres rapports locaux, fichiers runtime/cursors, `HYPOTHESIS_H1_LATENCY_CONVERGENCE.md`, `h1_latency_convergence_probe.py` sont exclus et préservés. Les anomalies d'accès aux anciens répertoires vendor ne sont ni corrigées ni ajoutées au commit.

Huit fichiers protégés inchangés, notamment Genesis DB/code, BTC V1, clob_transport, risk.py, pools HTTP, RPC préparatoire et worker génération. Sizing, risk limits et architecture parallèle/WS persistent préservés. Aucun changement aux anciennes DB ou timestamps.

## Une qualification READ-ONLY suivante

Depuis la racine du dépôt, avec les prérequis read-only existants configurés :

```powershell
python -B .\analysis\qualify_post_genesis.py --target-machine --health-contract --shadow-calibration --calibration-shares 5
```

Une invocation, pas de boucle et pas de `--freshness-ms`. Non exécutée ici. Utilise les GET publics/authentifiés préexistants et RPC de lecture, écrit un nouveau rapport et éventuellement un checkpoint inventory ; ne modifie pas Genesis en mode health-contract. La signature d'authentification L2 existante n'est pas une signature de transaction. Aucun ordre, cancel, allowance ou transaction ; ne pas substituer le mode target-machine sans health-contract. Le rapport doit rester bloqué tant que calibration et current inventory manquent.

Le commit de cette refonte doit contenir exclusivement les sources/tests et ce dossier de preuves. Aucun push n'est demandé ni effectué ; son SHA est retourné dans le résumé final.
