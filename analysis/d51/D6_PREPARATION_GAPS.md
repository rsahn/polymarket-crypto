# Préparation D6 — contrôles statiques, aucune recherche exécutée

Le dataset historique et le premier smoke sont FAIL ; aucune partition n'est ouverte et aucun résultat économique examiné ici.

1. L'ancien SPLIT_LOCK.json appartient au dataset historique FAIL. Ne jamais le réutiliser pour D5.1. Son minimum annoncé de 30 marchés complets OOS par durée implique au moins 7,5 h de marchés 15m, avant purge/embargo. Une répartition 50/25/25 demanderait au moins 30 h, avant marges. Il ne faut pas annoncer qu'une collecte de 3 h suffit, ni traiter les marchés 5m/15m concomitants comme indépendants.
2. CAPACITY_PREPARATION_20260921.json extrapole la croissance réellement mesurée, avec scénario 2x et réserve 5 Gio. C'est un budget provisoire, pas une durée choisie : pics/WAL/exports/temporaire doivent être inclus avant lancement long. Une archive compressée ajoutée à une DB conservée ne réduit pas son occupation ; ne jamais promettre cette économie.
3. pipeline/convert.py remplace payload_json des BOOK par NULL. Le brut SQLite est donc indispensable à cet export actuel. Toute nouvelle archive primaire exige conservation de toutes colonnes/types/ordres/metadata et preuve de reconstruction/replay, sans suppression des sources existantes.
4. research/offline.py reste un prototype lié à l'ancien SPLIT_LOCK ; il filtre 5m et échantillonne le premier snapshot par 100 ms. Il ne constitue pas encore l'évaluation complète des familles C3, BONEREAPER_LIKE, D6_OPTIMIZED et H1–H8 exigée par le nouveau protocole. Prévoir un nouveau manifeste/adaptateur et prouver l'exécution/liquidité sur tous les événements nécessaires ; ne pas promouvoir ce prototype silencieusement.
5. Les données publiques Bonereaper, sémantique temporelle, frais et résolutions doivent être vérifiés pour la nouvelle fenêtre admissible. L'expiration n'est pas une preuve de règlement. Aucun inventaire privé ni avantage statistique n'est inféré.

Prochaine étape effective : stabilité horloge, nouveau smoke et sa revue. Les constats ci-dessus ne déclenchent ni collecte longue ni D6 ni Paper.
