# Amendement technique avant les résultats réels

20 septembre 2026, préparation toujours WAITING_FOR_CONVERSION.
La revue manuelle a trouvé que les snapshots portant reject_reason=CROSS_MARKET_REJECT étaient simplement ignorés avant Engine.observe. Ils doivent provoquer l'arrêt critique demandé par l'utilisateur, même entre deux snapshots échantillonnés.

Correction limitée à paper_runtime/runtime.py + test_safety.py : contrôle avant échantillonnage, ValueError critique propagée. Aucun changement du moteur, des paramètres, des partitions ou des replays. Aucun Paper démarré. Aucune intervention sur PID12408 ni sur SQLite D5.

Le verrou initial de prepare_chain.py conserve l'ancienne empreinte du runtime. Sa comparaison finale signalera donc CODE_CHANGED_DURING_PREPARATION_ANALYSIS. Ce signal ne doit pas être masqué. Les résultats de recherche restent à examiner avec les empreintes du moteur et des scripts de recherche inchangées ; retester le runtime corrigé et produire un nouveau manifeste de validation avant tout lancement. Le statut de cette chaîne ne suffira pas à valider Paper.
