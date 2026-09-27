# BTC V1 prospective protocol — closure assessment, 2026-09-27

**BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED**

La mission cite la baseline 962/61. Le dépôt vérifié contenait déjà le delivery e3afaea avec 980/65. Les mesures et les preuves exhaustives de ce delivery sont conservées et réutilisées par empreinte ; aucun second smoke identique, aucun nouveau chantier D6. Seuls trois tests complémentaires et les preuves ci-dessous sont ajoutés.

| Point demandé | Résultat |
|---|---|
| 1. HEAD / branche / baseline | Initial e3afaea993438274187ea239567e477a38fed7ff, d6-live-execution-staging. Delivery initial au-dessus de 3b4a296 : 6f13bec ; dernier delivery existant : e3afaea. [Baseline complète](BASELINE.json). |
| 2. Real V1 binding | REAL_V1_BINDING_NOT_QUALIFIED |
| 3. Passive binding possible | NO, pour les callbacks exposés : l'entrée est absente sur NO_EXIT_DEPTH et rotation. |
| 4. Observability revision required | YES : OBSERVABILITY_ONLY_V1_REVISION_REQUIRED. Candidate existante OBSERVABILITY_V1_R1 ; non adoptée. |
| 5. Anciens / nouveaux hashes | Fichiers V1 protégés identiques avant/après ; hash AST candidate distinct, voir détails plus bas. Aucun nouveau runner de production prétendument qualifié. |
| 6. Differential equivalence | ECONOMIC_BEHAVIOR_IDENTICAL=true sur les fixtures déjà scellées ; structures AST identiques après retrait des observations. Ni équivalence murale ni qualification réelle inférées. |
| 7. Depth reuse | DEPTH_REUSE_UNQUALIFIED pour l'ensemble V1/protocole. Le modèle prospectif seul passe conservation/restart/refus, mais ne peut accepter le second fill V1 inchangé. |
| 8. Fee model | MARKET_FEE_UNQUALIFIED, deux tokens. |
| 9. Propriété inconnue | Arrondi exact aux frontières, agrégation des matches/niveaux et allocation sur partial fills. [Relecture officielle](FEE_RECHECK.json). |
| 10. STORAGE_BREAKDOWN | [Tableau avec toutes les colonnes demandées](STORAGE_BREAKDOWN.md) ; [bytes et paths mesurés](STORAGE_BREAKDOWN.json). Réutilisation de l'inventaire exhaustif, zéro estimation de volume. |
| 11. Lossless reduction | LOSSLESS_STORAGE_QUALIFIED pour la conservation du codec testé : capture complète et journal synthétique jusqu'au ledger. Cela ne qualifie pas les données/fees manquantes du binding réel. |
| 12. Smoke technique | Smoke unique déjà terminé : 1320.0542836000677 s de capture, 3973286 lignes / 1336887 événements, 336113918 bytes, 254621.285030 bytes/s de capture, ratio ×14.282847. |
| 13. Projection 168 h | Dataset archive seul 153994953187 bytes ; journal réel et checkpoints réels UNPROVEN, jamais mis à zéro. |
| 14. Required free space | Minimum 369587887649 bytes avec 2× puis +20 %. Libre mesuré 47134601216 bytes ; déficit minimal 322453286433 bytes. Total qualifié inconnu. STORAGE_UNQUALIFIED. |
| 15. Replay capacity | REPLAY_CAPACITY_UNQUALIFIED pour le ledger hebdomadaire ; archive streaming PASS. Mesures ci-dessous. |
| 16. Targeted tests | 21 PASS / 18 subtests / 0 FAIL. [Résultat](TARGETED_RESULT.json). |
| 17. Full suite | 983 PASS / 79 subtests / 0 FAIL ; 109 fichiers. [Log](FULL_SUITE.log), [validation et empreintes](VALIDATION.json). |
| 18. Audit | PASS du périmètre livré, distinct de readiness ; [AUDIT.json](AUDIT.json). |
| 19. Leak scan | PASS sur les nouveaux fichiers avant commit ; aucun secret ni DB ajouté. |
| 20. Criteria | Hash inchangé, voir ci-dessous ; 72/48/48 h et embargo 60 s inchangés. |
| 21. D6 | SYSTEM_READY=false, current_inventory_proven=false conservés ; aucun composant D6 modifié. |
| 22. Flags | REAL_ORDERS_ENABLED=false, LIVE_EXECUTION_ARMED=false, submit_allowed=false. |
| 23. SDK | monetary SDK attempts=0, 16 méthodes gardées ; aucun ordre/signature/cancel/transaction/allowance update. |
| 24. Commit | Nouveau commit séparé après contrôles ; SHA exact retourné dans la réponse de livraison. Les ancêtres 3b4a296, 6f13bec et e3afaea sont préservés. |
| 25. Push | Non effectué : le refus précédent du contrôle automatique sur la publication publique reste en attente d'une autorisation explicite. La mission réitère le push mais ne répond pas à cette demande précise d'exposition publique. Aucun contournement ni nouvelle tentative. |
| 26. Verdict | BTC_V1_PROSPECTIVE_PROTOCOL_BLOCKED |
| 27. Commande PowerShell de collecte | Aucune, car pas READY. Aucun TRAIN, VALIDATION, OOS ou PAPER économique lancé. |

## Preuve complémentaire de bout en bout

Le nouveau test produit un journal synthétique complet de 20 observations : entrée à plusieurs prix, frais annotés sans double débit, marks, sortie partielle, résiduel, résolution explicite puis fin de session.
Encodage, stockage, relecture, vérification de la chaîne de journal et replay reproduisent exactement les bytes, événements, timestamps, identités de partition, books, niveaux consommés, fills, frais de fixture, résiduels et ledger final.
SHA canonique avant = après : **919b06f872619e975d99ab037fdc239d7995a19316839b99617cc10a9ad8cf45**.
[ROUNDTRIP_LEDGER.json](ROUNDTRIP_LEDGER.json).
Ce fixture n'est pas un dataset économique ; son label de schéma TRAIN ne constitue pas une ouverture réelle.
Le fee policy est explicitement SYNTHETIC_ONLY : aucune précision réelle inventée.

## Incompatibilité qui empêche de fermer le binding

Le test extrait la fonction fill du runner V1 exact. Sur [[0.5, 50]], deux budgets FIXED25 donnent chacun 50 shares ; le book n'est pas muté.
Le contrat BookTape existant consomme 50 lors de la première opportunité, puis 0 sur la deuxième observation identique.
Observer le second fill sans l'accepter dans le ledger préserve V1, mais invalide la qualification de l'expérience. Le réduire à 0 ou reconstituer du volume modifierait les règles interdites dans cette mission.
Un hook peut rendre l'entrée visible, pas résoudre cette divergence économique. Aucun tel changement n'a été fait.

[Différentiel déjà scellé](../blockers_20260926/DIFFERENTIAL.json) : mêmes signaux UP/DOWN, timestamps, ordre des opportunités, entrées/sorties, prix/quantités, résiduels et résultat simulé sur fixtures normale, partielle, NO_EXIT_DEPTH et rotation. Observations supplémentaires seulement. La candidate reste non adoptée.

## Frais : état de la preuve

La [documentation officielle](https://docs.polymarket.com/trading/fees) relue fournit la formule C × feeRate × p × (1-p), les cinq décimales et le minimum affiché ; elle ne suffit pas à spécifier les cas limites et l'agrégation exacte du ledger.
Les preuves Gamma/CLOB/SDK et leurs limites restent [celles scellées précédemment](../blockers_20260926/FEE_QUALIFICATION.md).
Le nouveau test vérifie les deux tokens aux prix 0.01, 0.49, 0.50, 0.51, 0.99 et aux quantités frontières/partielles : chaque calcul réel est refusé tant que la règle exacte reste inconnue. Aucun fallback fee=0.

## Stockage et replay : mesures conservées

[Smoke mesuré](../blockers_20260926/STORAGE_SMOKE.json) : capture de 22 minutes complète, choisie avant traitement ; conversion offline NO-TRADE, pas nouvelle collecte réseau.
4 800 663 552 bytes SQLite deviennent 336 113 918 bytes d'archive ; SHA complet des valeurs restaurées 9b62642be7ae706a09637a8dd27f662e5ce2d0f96cdc259dcf76e711f92f0e30.
Aucun événement/doublon/timestamp supprimé. Aucune nouvelle déduplication adoptée.
Framing/footer 447701 bytes ; ce n'est pas le journal économique. Les checkpoints/journaux futurs ne sont pas qualifiés par les petits fixtures.
Les annexes d'audit d'origine restent hors des 4.8 GB et sont listées séparément.

Replay : 252.695122 s, 15723.636 lignes/s,
1330116.369 bytes/s d'archive compressée,
25767455.620 bytes/s de flux logique encodé ; pic RSS 79486976 bytes.
[Probe journal/state-copy](../blockers_20260926/REPLAY_PROBE.json) : récupération exacte à 5001 événements en 0.204315 s puis replay adapter 0.075882 s, pic RSS 45551616 bytes ; coût médian copie à 5000 événements ~59.67 ms.
Ces coûts et l'historique O(N) conservé démontrent que la lecture streaming de l'archive ne qualifie pas le ledger hebdomadaire. Aucune projection aveugle du petit journal MARK vers une semaine.

[Capacité réactualisée](STORAGE_CAPACITY.json) : manque minimal **322453286433 bytes = 322.453286433 GB = 0.322453286433 TB**. Ce minimum n'est pas un total exact qualifié ; journal/checkpoints restent inconnus.

## Empreintes conservées

- paper_live.py avant/après : 5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364
- runner avant/après : a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405
- candidate AST OBSERVABILITY_V1_R1 (type d'empreinte distinct, non adoptée) : ceaa1974edd442eedb94c038940cdcd0a8e987139b58a55316a8cc855680d6ef
- Genesis avant/après : 5365085da95cecb49fa4c922b890e9803ef223fdefef541505c2dc5a3de7814f
- critères avant/après : 869a386b9112a572247e3fb61ffbf4a27afb20493a791929e72f52bc0d9cd06a

Les trois seuls blockers restants sont le binding réel (incluant le conflit de profondeur), les frais exacts, et le stockage/replay hebdomadaire. Les tests verts ne les transforment pas en READY.
