# D6: resumable inventory preparation â€” 26 septembre 2026

## TAIL_SCAN_ROOT_CAUSE

**SCAN_TOTAL_BLOCK_LIMIT**, avant le premier appel eth_getLogs. Le scanner historique refuse `end-start >= 50000`, soit plus de 50 000 blocs inclusifs par invocation. `fixed_scan` envoyait le backlog entier au scanner ; son motif Ã©tait Ã©crasÃ© en CTF_READ_RANGE_SCHEMA_OR_CHAIN_FAILED puis TAIL_SCAN_FAILED.

Le rapport de rÃ©fÃ©rence montre sept RPC PASS (chain/finalized/latest/rechecks/Genesis/cursor), zÃ©ro requÃªte logs, zÃ©ro erreur HTTP/RPC/429, retries=0, failure_reason=null. Span des RPC : 1302 ms, trÃ¨s infÃ©rieur au budget de dispatch 120 s. Pas de preuve de timeout, cancellation, starvation ou saturation provider. Le chemin d'appel vÃ©rifie dÃ©jÃ  l'ordre des bornes et impose log_window=10 : le rejet local du total est la cause compatible avec ce point exact d'arrÃªt. Reproduction avec le code du commit de base et le backlog relu : mÃªme BLOCKED, zÃ©ro RPC tentÃ© (TAIL_SCAN_ROOT_CAUSE.json).

Les 13 704 blocs 94 424 638..94 438 341 sont **dÃ©jÃ  couverts**, pas le backlog du run Ã©chouÃ©. Sa frontiÃ¨re finalized exacte n'a pas Ã©tÃ© conservÃ©e par l'ancien rapport ; aucun chiffre exact rÃ©troactif n'est inventÃ©.

## Cursor, backlog et couverture

Checkpoint : runtime/d6_inventory_cursors/94438341_f0ecb179baf44aeb8e5598fe65463a7c.json, schema 1. Checksum et liaison Genesis vÃ©rifiÃ©s. Hash relu via le provider public configurÃ© par analysis/run_d6_public_readiness.ps1 :

`94438341 / 0x6277908209d7634b1edcfc7f278fd48d1b2fa839292e24751bd3bd6b25a803ad`.

FrontiÃ¨re finalized observÃ©e Ã  1790443728701 ms : `94492389 / 0x045f8dd00628006cb3bd5a83bae4c9515109f973b2bb7167921454b87742a102`. Backlog exact Ã  cette observation : **54 048 blocs**, cursor+1=94 438 342. Ce nombre augmente avec la chaÃ®ne ; ce n'est pas une lecture perpÃ©tuellement actuelle.

Plan Ã  cette frontiÃ¨re : **5 405 fenÃªtres de logs de 10 blocs maximum**, rÃ©parties en **109 tranches checkpointables de 500 blocs maximum**. Ce dÃ©coupage est un budget de prÃ©paration, pas un SLA temporel ni une limite du total Ã  couvrir. La constante globale de fraÃ®cheur n'est pas rÃ©introduite.

Pour le run historique : 0 fenÃªtre exÃ©cutÃ©e/rÃ©ussie/Ã©chouÃ©e cÃ´tÃ© provider ; premiÃ¨re fenÃªtre non exÃ©cutÃ©e 94 438 342..94 438 351. Le rejet Ã©tait avant dispatch. La derniÃ¨re tranche du checkpoint existant (parent 94 437 884 â†’ ancre 94 438 326 â†’ C 94 438 341) a Ã©tÃ© revalidÃ©e sans gap/overlap avec evaluate_boundary Ã  son instant d'acquisition original. Il ne s'agit pas d'un retiming : le rÃ©sultat est une revalidation de preuve historique, non une nouvelle gÃ©nÃ©ration.

## Architecture retenue

- Bootstrap public-only indÃ©pendant : une frontiÃ¨re finalized qualifiÃ©e et fixe pour chaque cycle ; scan consÃ©cutif exact cursor+1..frontiÃ¨re.
- Tranches de checkpoint de 500 blocs ; requÃªtes logs toujours <=10 blocs. Aucune troncature du backlog total. Garder la limite locale de 50 000 par invocation du scanner ne gÃªne plus le bootstrap.
- Une seule requÃªte en vol, 200 ms minimum entre dÃ©parts. Budget existant de 120 s **par tranche**, non imposÃ© au bootstrap entier. Au plus trois tentatives par lecture pour TIMEOUT, CONNECTION_ERROR, HTTP 500/502/503/504 et RATE_LIMIT/429 ; attentes bornÃ©es 200/400 ms en plus du pacing. Autres erreurs bloquantes, messages bruts jamais propagÃ©s.
- RANGE_LIMIT explicite ou HTTP413 sur eth_getLogs : subdivision binaire, mÃªme filtre CTF et mÃªmes bornes agrÃ©gÃ©es ; un bloc indivisible qui Ã©choue bloque. Aucun trou ignorÃ©.
- Mode worker foreground `--watch --poll-seconds <valeur explicite>` : cycles successifs, pool HTTP rÃ©utilisÃ© Ã  l'intÃ©rieur d'un cycle, relecture du meilleur checkpoint Ã  chaque cycle, arrÃªt sur erreur. Verrou OS exclusif libÃ©rÃ© automatiquement en cas de crash. Aucun daemon ni automation dÃ©marrÃ© ici.
- Readiness dirige un backlog > une tranche vers BOOTSTRAP_CATCHUP_REQUIRED au lieu de le scanner dans sa prÃ©paration. Ce routage ne donne aucun PASS. La petite queue/fixed-C et D6_SEMANTIC_V1 restent distincts. Le rapport indique generation_created/downstream_checks_qualified ; absence de gÃ©nÃ©ration = aucun sample shadow ajoutÃ©.

## Checkpoint atomique et reprise

Schema 2 : checksum de l'inventaire et de son acquisition, liaison au snapshot Genesis, chain137, wallet, contrat CTF, scope incoming conservÃ©, parent block/hash/checksum, frontiÃ¨re/hash, derniÃ¨re tranche complÃ¨te, toutes ses fenÃªtres, timestamps originaux, actifs/balances connus et compteur d'Ã©vÃ©nements. Ã‰criture fichier temporaire, flush+fsync puis publication hard-link atomique sans Ã©crasement ; les anciennes preuves sont conservÃ©es.

Cursor et extrÃ©mitÃ© de tranche revÃ©rifiÃ©s canoniquement avant/aprÃ¨s le scan ; Genesis vÃ©rifiÃ©. Aucune publication aprÃ¨s Ã©chec partiel, removed log, reorg, trou ou overlap. Reprise au dernier checkpoint complet. Chargement schema2 vÃ©rifie Ã©galement la prÃ©sence et l'identitÃ© du parent dans les preuves locales ; conflit de hash/balances/events au mÃªme bloc bloque.

Les historiques schema1 restent des ancres scopÃ©es existantes, jamais transformÃ©es en preuve globale. Dans cette phase de baseline vide, dÃ©couverte d'activitÃ©/solde non nul => RECOVERY_REQUIRED, pas de projection comptable inventÃ©e ni de checkpoint de succÃ¨s. Les checkpoints publiÃ©s prÃ©servent le scope CTF ; ils n'attestent pas tous les protocoles de positions ni toute l'histoire distante.

## Mesure provider

Mesure isolÃ©e **sans checkpoint** de 94 492 370..94 492 389 : 2 fenÃªtres PASS, 20 blocs, 6 RPC, wall 1097,08 ms, p50 RPC 123 ms, 18,23 blocs/s et 1,823 fenÃªtres/s. ZÃ©ro retry/rate limit. p95 non publiÃ© : Ã©chantillon de six RPC insuffisant. Ce micro-Ã©chantillon ne mesure pas le bootstrap complet et ne justifie pas d'augmenter la concurrence. Aucune accÃ©lÃ©ration arbitraire appliquÃ©e.

La mesure ne couvre pas l'intervalle entre le cursor et cette fenÃªtre ; **le cursor rÃ©el n'a pas avancÃ©**. Le bootstrap complet et une nouvelle gÃ©nÃ©ration D6 restent Ã  exÃ©cuter. Aucun rÃ©sultat de test synthÃ©tique n'est prÃ©sentÃ© comme une collecte rÃ©elle.

## Tests, audit, intÃ©gritÃ©

RED : module absent avant correction. GREEN : 27 tests catch-up/worker couvrent petit/gros backlog (>10k et >50k), identitÃ© cursor, trous/overlaps, division sur limite provider, retries transitoires/exhaustion, erreur permanente, pacing, crash milieu tranche et reprise, removed logs/reorg, preuve jusqu'Ã  C sans current, contexte1300 inopÃ©rant, Genesis inchangÃ©, flags et verrou OS, absence de sample sans gÃ©nÃ©ration. Suite complÃ¨te et audit dans FULL_FINAL.log et AUDIT.log. Les anciens tests de pacing/fenÃªtres restent prÃ©sents : le scan > une tranche est testÃ© hors du chemin readiness.

INTEGRITY.json confirme les hashes protÃ©gÃ©s inchangÃ©s : Genesis DB/code, BTC V1 et son runner, sizing/contrÃ´leur, risk, WS, readiness et D6_SEMANTIC_V1. BASELINE.json identifie les fichiers prÃ©existants exclus du commit. Seules deux tÃ©lÃ©mÃ©tries D5 ont continuÃ© d'Ã©voluer extÃ©rieurement ; aucune Ã©criture ni restauration par cette correction. Le leak scan par motifs n'a trouvÃ© aucune clÃ© privÃ©e, secret assignÃ© ou URL Ã  token ; il ne constitue pas une preuve mathÃ©matique d'absence de fuite.

REAL_ORDERS_ENABLED=false, LIVE_EXECUTION_ARMED=false, submit_allowed=false. Aucun ordre/cancel/update allowance/transaction ; aucune clÃ© privÃ©e ni credential L2 chargÃ© par le bootstrap. Aucun changement de SLA ni nouvelle qualification lancÃ©e. Au succÃ¨s futur, inventory_through_C_proven ne signifie que couverture scopÃ©e jusqu'Ã  la frontiÃ¨re ; **current_inventory_proven=false**, post_C_completeness=NO_COMMON_POST_C_COMPLETENESS_WATERMARK et INVENTORY_UNPROVEN restent bloquants.

## Une prochaine commande

```powershell
& 'C:\Users\Ramy\Documents\polymarket-crypto\analysis\run_d6_inventory_bootstrap.ps1'
```

Une invocation bootstrap sur le mÃªme provider public dÃ©jÃ  utilisÃ©. Publie uniquement des nouveaux checkpoints complets et un rapport D6_INVENTORY_CATCHUP_<UTC>.json. La frontiÃ¨re sera sÃ©lectionnÃ©e de nouveau au dÃ©marrage et le backlog rapportÃ© exactement. Le script termine en erreur si un maillon manque ; les checkpoints complets antÃ©rieurs restent exploitables. Ne lancer une qualification suivante qu'aprÃ¨s succÃ¨s dÃ©montrÃ© du bootstrap. Aucune commande de qualification n'est donnÃ©e prÃ©maturÃ©ment ici.
