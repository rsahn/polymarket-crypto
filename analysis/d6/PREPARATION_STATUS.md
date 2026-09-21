# D6 PAPER500 — préparation, aucun Paper démarré

Mission applicable : MAIN_MISSION_PAPER500_20260920.md. L'audit D5 PID12408 reste intact et indépendant. Données D5 « prospective D5 short-window dataset », jamais validation24h.

## Pipeline réel

Résoudre pipeline/active.json pour trouver progress.json et conversion_report.json. Le dossier original data est conservé après l'erreur Windows de remplacement d'un statut. data_recovered_20260920 réutilise son préfixe Parquet vérifié et continue la lecture SQLite en mode ro/query_only. Aucun timestamp ni fichier D5 réécrit. Le temps total doit additionner l'exécution originale et la reprise, sans afficher le temps de reprise comme temps total.

Les 7 518 713 événements sont exportés. Les 14 882 424 côtés de carnet sont en cours. Ensuite : anchors/hedge_attempts, SHA source, BTC structurel, jointure features DuckDB. La conversion n'est pas un PASS qualité D5.

## Partitions et candidat avant résultats

SPLIT_LOCK.json + SHA : 5m TRAIN17, VALIDATION9, OOS10 fermé ; 15m TRAIN5, VALIDATION3, OOS3 fermé ; deux marchés partiels par durée exclus. Bornes UTC12:15/13:00. Aucun slug partagé. OOS historique trop petit pour une validation forte ; non ouvert. La future expérience Paper pourra être l'OOS principal, après sécurité et autorisation.

Candidat déterministe : momentum BTC5s normalisé par3bps (40%), différence des imbalances de profondeur (30%), réduction du déséquilibre d'inventaire (20%), opportunité de paire orientée vers réduction de l'inventaire (10%). Aucune décision avant début de la fenêtre5m (comme dans le replay). Seuil absolu0.25, cooldown3s, spread<=0.04, profondeur>=5. Le signal de paire ne constitue pas une règle unique pair_cost<1. Poids/paramètres fixés avant résultats, aucun grid search. Réduction de la position opposée prioritaire.

Capital virtuel500, réserve100, coût détenu/market<=50, ordre<=5shares, résidu directionnel<=20shares, drawdown conservateur25, latence250ms. Sensibilités0/100/500ms ; jamais sélection sur0ms seulement. Frais crypto0.07*p*(1-p)*shares, arrondis vers le haut à5décimales par niveau, comptabilisés en USDC virtuels : approximation prudente explicitement distincte d'un fill réel.

Replay Parquet : premier snapshot de chaque bucket100ms, horodatage d'origine conservé. Traitement en event_id/temps disponible, générations et invalidations. Profondeur consommée non réutilisée ; les observations omises rendent ce modèle conservateur mais ne reproduisent pas tous les événements. Exécution au premier snapshot admissible après arrivée : latence réalisée parfois supérieure à la consigne. Aucun settlement fabriqué depuis l'échéance : résolution contemporaine non disponible => capital bloqué, equity potentiellement UNKNOWN. Aucun gain ne sera déduit d'une valeur inconnue.

Baselines : RANDOM_SIDE(seed42), ALWAYS_CHEAPER_SIDE, ALWAYS_REBALANCE(tieUP), FIXED_ALTERNATING, PAIR_COST_THRESHOLD(<0.98), WAIT_ONLY. TRAIN et VALIDATION ont des portefeuilles simulés indépendants de500 ; ce zéro initial virtuel ne représente pas l'inventaire Bonereaper.

## Bonereaper

Extraction publique555 opérations dont345BTC, identités vérifiées, brut et SHA conservés. Jointure contextuelle strictement avant début_seconde_API-100ms, tous temps source/réception/disponibilité, identité, génération et fraîcheur<=1000ms. Ce décalage ne prouve pas ce que voyait le trader avant sa décision privée. Inventaire initial UNKNOWN : H1/H2/H3/H6 et dépendance au cash deH8 non identifiables. H4/H5/H7/H8 descriptifs, observations dépendantes par marché, aucune causalité ni significativité prétendue. Aucune consultation de l'OOS verrouillé.

## Runtime préparé

Aucun client d'ordre, signature ou wallet. Feeds publics uniquement. Variables LIVE/REAL refusées. start_gate exige verdict technique, empreinte exacte du code/paramètres et rapport D5 réellement accepté. Contrôle NTP Windows/Cloudflare, deux séries<=100ms, W32Time Running ; aucune correction d'horloge. Recontrôle30min, jump wall/monotonic>500ms=>arrêt. Frais de chaque marché vérifiés ; inconnus=>arrêt. Feed perdu30s, DB inaccessible, cash/inventaire incohérent, cross-market, disque<5Gio, changement stratégie ou drawdown=>FAILED avec fermeture et rapport autant que le stockage le permet.

Journal SQLite Paper séparé : contexte, features, décisions, simulation, inventaire, résolution publique avec preuve et horodatage. Aucune libération du capital à la seule échéance. Arrêt demandé via fichier STOP_REQUESTED dans le nouveau dossier de session. Fin automatique24h, rapport JSON/MD. PnL par heure sur points observés ; attribution du PnL par régime non identifiée sans règle de lots, affichée UNKNOWN avec activité/frais par régime plutôt qu'inventée.

Dashboard http://127.0.0.1:8766/ : lecture seule, préparé, aucune session en cours. Les tirets sont des données absentes, pas des résultats simulés. Les métriques réelles ne s'afficheront qu'après lancement autorisé.

## État de validation

22 tests moteur/runtime PASS,3 tests conversion PASS,3 tests recherche/jointure PASS sur fixtures. Cela ne valide ni l'edge ni la base réelle. Comparaisons et jointure réelles en attente de conversion. Historique audit/replays toujours attendus. OFFLINE_VERDICT reste WAITING_FOR_D5_AUDIT. Aucun Paper lancé ; l'autorisation finale ne sera demandée qu'une fois les preuves et la configuration revues.

Chaîne de préparation réelle lancée (research/active.json). Un correctif cross-market du runtime a été apporté avant résultats ; PRE_RESULT_SAFETY_AMENDMENT.md et SAFETY_AMENDMENT_MANIFEST.json documentent exactement deux fichiers modifiés. Moteur et recherche inchangés. La comparaison de verrou finale doit conserver le signal de changement et être revue explicitement.
