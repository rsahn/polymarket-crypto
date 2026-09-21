# D6 — préparation PAPER500

Verdict : **WAITING_FOR_D5_AUDIT**. Aucun Paper démarré. Aucune rentabilité démontrée. Le candidat peut seulement être proposé pour une expérience prospective après revue D5 acceptée et autorisation explicite de lancement.

## 1. Pipeline terminé

Conversion + contrôles essentiels + features : **49.90 min**, incidents/reprises inclus. Source26,186,612,736 octets ; Parquet844,931,462 octets. 7,518,713 événements,14,882,424 côtés,7,441,212 BOOK et autant de features. Marchés38×5m et13×15m. Zéro enveloppe post-échéance dans ce contrôle essentiel. SHA source `e4f7212036818141c86e2d45c0082adaa834126f61db3060c3809264c588d0bd`. Source taille/mtime inchangées. Reprise finale exclusivement Parquet. Détail : PIPELINE_REPORT.md et data_final_20260920/conversion_report.json.

## 2. Audit D5 : reprise supervisee en cours

Ancien PID12408 arrete avec autorisation explicite et sauvegarde de ses preuves : OLD_AUDIT_ABORTED_BY_USER_FOR_PERFORMANCE. L'auditor_next complet du dossier `analysis/d5/full_review_20260920_201805` a termine PASS, mais cette revue est restee incomplete apres une limite operationnelle d'une heure pendant integrity_check. Ce timeout ne prouve aucun defaut des donnees.

Reprise actuelle : `analysis/d5/resumed_review_20260920_214402`, PID14672 au lancement, cache SQLite128Mio en lecture seule, alerte d'une heure sans interruption automatique. Integrity_check complet, foreign keys, metriques source, deux nouveaux replays NoTrade500 et comparaison complete sont en cours/attente. Superviseur complementaire PID17852 au lancement : attend la sortie de cette revue, puis attestation SHA source et controles des timestamps acceptes/gaps. Le compteur actualise est http://127.0.0.1:8767/ ; les PID doivent toujours etre reverifies.

La reutilisation du PASS auditor_next reste conditionnee aux preuves de provenance/code et au SHA source actualise. Aucun D5 PASS global n'est acquis. Les quelques gaps >5s et les avertissements W32Time bruts seront examines sans assouplissement implicite des criteres. Dataset d'environ3h02m24.725s utiles, jamais24h. Le statut brut FAILED/KeyboardInterrupt est conserve ; les marqueurs de fermeture seuls ne suffisent pas a valider D5.

Le protocole prioritaire est `analysis/AUTONOMOUS_SUPERVISOR_PROTOCOL_20260920.md`. Aucune nouvelle analyse D6/OOS avant D5 PASS. Paper reste non demarre et requerra une autorisation explicite, meme au jalon PAPER500_READY_FOR_USER_APPROVAL.

## 3. Chronologie et OOS

Partitions figées avant résultats par slug : TRAIN17×5m+5×15m ; VALIDATION9×5m+3×15m ; OOS10×5m+3×15m fermé ;2 marchés partiels exclus par durée. BornesUTC12:15/13:00. Aucun slug partagé, aucun OOS ouvert. Effectif insuffisant pour validation forte ; l’expérience Paper future peut être l’OOS prospectif principal selon la mission. La latence250ms et les paramètres n’ont pas été choisis après résultats.

## 4. Bonereaper contemporain

555 opérations publiques extraites dont345BTC ; brut, métadonnées, identités et SHA conservés dans bonereaper_contemporary. Inventaire initialUNKNOWN. Aucune reconstruction fictive. Borne contextuelle strictement antérieure à bin_start-100ms, identité/génération, tous timestamps et fraîcheur1s. Cette règle ne prouve pas l’état privé avant la décision du trader.

Sur 228 opérations éligibles TRAIN/VALIDATION, **17** sont jointes :3TRAIN sur2marchés et14VALIDATION sur7marchés. Motifs exclus : {'NO_ACTIVE_MATCHING_GENERATION': 33, 'NO_FRESH_CAUSAL_BOOK': 178}. Couverture trop faible pour conclure à une règle de trading. Aucune jointure15m exploitable dans ces partitions.

H1/H2/H3/H6 : non identifiables sans inventaire initial. H4/H5 : associations descriptives sur effectif minuscule, aucune causalité/significativité. H7 : comptages par tiers, sans correction d’exposition temporelle donc pas un taux d’arrivée. H8 : tailles et corrélations contextuelles descriptives ; cash privé/inventaire inconnus. Rapport complet et provenance : research/prepared_final_20260920/context/JOIN_REPORT.json et JOINED_CONTEXT.json. Sources publiques : [profil](https://polymarket.com/fr/@bonereaper), APIactivité publique data-api.polymarket.com/activity (requêtes exactes et réponses brutes archivées), Gamma pour les identités.

## 5. Candidat et latences

Portefeuille500 indépendant par partition/modèle. Réserve100, coût détenu/market<=50, ordre<=5shares, résidu<=20shares, seuil d’arrêt drawdown25 (un saut de valorisation peut dépasser le seuil avant arrêt). Frais conservateurs0.07*p*(1-p)*shares, arrondis vers le haut par niveau. Profondeur partielle, aucun short, pas de capital libéré sur seule échéance. Moteur/public feed uniquement, aucune voie ordre réel.

| Partition | Latence ms | Ordres | Fills de niveau | Cash final | PnL final | MaxDD prudent |
|---|---:|---:|---:|---:|---|---:|
| TRAIN | 0 | 8 | 8 | 490.43974 | UNKNOWN | 14.55491 |
| TRAIN | 100 | 8 | 7 | 495.09671 | UNKNOWN | 10.45665 |
| TRAIN | 250 | 8 | 6 | 500.03915 | 0.039150000 | 5.48639 |
| TRAIN | 500 | 7 | 5 | 494.66974 | UNKNOWN | 10.45665 |
| VALIDATION | 0 | 2 | 3 | 497.78925 | UNKNOWN | 2.21075 |
| VALIDATION | 100 | 2 | 2 | 497.23761 | UNKNOWN | 2.76239 |
| VALIDATION | 250 | 2 | 2 | 497.23761 | UNKNOWN | 2.76239 |
| VALIDATION | 500 | 2 | 1 | 499.46850 | UNKNOWN | 0.75296 |

À250ms : +0.03915USDC en TRAIN, seulement6 fills de niveau ; VALIDATION a2ordres/2fills, cash497.23761 et PnL finalUNKNOWN (inventaire non réglé). Le cash n’est pas le capital final. Ces résultats ne prouvent aucun edge ni supériorité. Pas de sélection sur le résultat0ms.

## 6. Baselines et correction de revue

Six règles comparées : RANDOM_SIDE, ALWAYS_CHEAPER_SIDE, ALWAYS_REBALANCE, FIXED_ALTERNATING, PAIR_COST_THRESHOLD et WAIT_ONLY. Seuil de drawdown appliqué après correction de la première version du replay qui l’omettait. Anciennes sorties conservées ; elles ne servent plus de comparaison finale. RISK_CORRECTION_LOCK.json documente la correction, le cache réutilisé et le moteur inchangé. Décisions et exécutions du candidat identiques aux huit cas précédents (2partitions×4latences). Aucun recalage de paramètres.

| Partition | Baseline | Ordres | Cash | PnL final | Arrêt drawdown |
|---|---|---:|---:|---|---|
| TRAIN | RANDOM_SIDE_250 | 129 | 350.66399 | UNKNOWN | OUI |
| TRAIN | ALWAYS_CHEAPER_SIDE_250 | 101 | 443.40202 | UNKNOWN | OUI |
| TRAIN | ALWAYS_REBALANCE_250 | 167 | 249.43322 | UNKNOWN | NON |
| TRAIN | FIXED_ALTERNATING_250 | 108 | 334.40656 | UNKNOWN | OUI |
| TRAIN | PAIR_COST_THRESHOLD_250 | 0 | 500.00000 | 0 | NON |
| TRAIN | WAIT_ONLY_250 | 0 | 500.00000 | 0 | NON |
| VALIDATION | RANDOM_SIDE_250 | 82 | 364.35179 | UNKNOWN | OUI |
| VALIDATION | ALWAYS_CHEAPER_SIDE_250 | 90 | 467.24129 | UNKNOWN | OUI |
| VALIDATION | ALWAYS_REBALANCE_250 | 133 | 261.39459 | UNKNOWN | NON |
| VALIDATION | FIXED_ALTERNATING_250 | 69 | 380.28213 | UNKNOWN | OUI |
| VALIDATION | PAIR_COST_THRESHOLD_250 | 0 | 500.00000 | 0 | NON |
| VALIDATION | WAIT_ONLY_250 | 0 | 500.00000 | 0 | NON |

Aucun classement de rentabilité quand le PnL estUNKNOWN. Les baselines arrêtées sont valorisées à leur arrêt, pas artificiellement prolongées jusqu’à fin de partition. Aucune résolution future utilisée. Le replay échantillonne le premier BOOK par100ms, conserve son timestamp et exécute au premier snapshot admissible après arrivée ; la latence observée peut excéder la consigne. Les replenishments manqués rendent la simulation conservatrice, elle ne reproduit pas chaque message brut. Résultats définitifs de cette revue : research/risk_corrected_20260920/OFFLINE_COMPARISON.json ; contrôles comptables et empreintes : REVIEW_CHECKS.json. Recalcul corrigé205.24s.

## 7. Tests et runtime

29 tests synthétiques : pipeline4, moteur/runtime22, recherche/jointure3. Test ajouté au replay existant : arrêt effectif après drawdown, pas d’ordre ultérieur. Contrôles finaux sur tous portefeuilles : cash>=100, inventaire>=0, exposition<=20, coût/market<=50, identité cash+coûts détenus=500+réalisé ; aucun écart. Ces contrôles ne remplacent pas D5.

Runtime préparé : NTPdeux séries/two hosts<=100ms etW32TimeRunning, suivi30min, jump horloge500ms ; fees inconnus/refus, cross-marketcritique y compris rejets wire, feed perdu30s, DB indisponible, incohérence comptable, disque<5Gio, stratégie changée etdrawdown=>arrêt. Verrou empreinte exacte code/paramètres, journal complet, settlement public vérifié et post-échéance, fin24h et rapportsJSON/MD. VariablesLIVE/REAL rejetées. Aucun wallet/client d’ordre. Tests de clôture sur feeds fictifs seulement ; aucune expérience24h réalisée.

## 8. Dashboard et limites restantes

Dashboard local [D6](http://127.0.0.1:8766/) en lecture seule, noir/magenta, métriques absentes tant que Paper n’a pas démarré. Aucun bouton d’achat/vente/LIVE. Équité/drawdown, BTC, carnet, inventaire, signaux, exécutions et performance viennent des états/journaux, aucune confidenceIA inventée. PnLtoday enUTC. Rapport par heure basé sur points observés. PnL par régime non attribué faute de règle de lots figée : UNKNOWN, avec activité/frais par régime ; pas de métrique financière décorative. Aucun prétendu Paper_READY complet.

## 9. Décision

WAITING_FOR_D5_AUDIT. Préparation/recherches courtes terminées, pas de validation forte et pas de Paper. Ne pas demander une autorisation prématurée pour contourner une anomalie. À réception du verdict D5 : examiner les contrôles et les deux replays, conserver les défauts, puis présenter si admissible le candidat expérimental figé pour une autorisation explicite24h/PAPER500. Jamais LIVE ou argent réel.
