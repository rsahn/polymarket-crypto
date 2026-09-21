# Cinquième smoke — décision avant collecte

Nouvelle collecte1320s (22min),nouvelleDB,SHADOW/NO_TRADE500. Même protocole qualité D5.1,aucun seuil relâché,aucune reconnexion forcée,aucun abandon de file ni retiming. Deux contrôles NTP frais avant puis surveillance toutes300s et après. Revue complète8étapes aprèsfermeture ; backend,runner,HEAD figés pendant collecte+revue.

Modifications depuis le quatrième smoke : index de doublons conservant exactement la fenêtre2048 ; cache exact1024profondeurs schéma2 (bits de flottants comme clé, données persistées inchangées) ; compteurs séparés wall/threadCPU de normalisation/callback avec écriture/commit.186testsPASS.77477snapshots équivalents et persistance exhaustive sur bases techniques équivalente. Les sérialiseurs natifs testés restent hors backend.

Débit technique baseline1534/s,aprèsindex1658/s,cache1754/s ; mesures individuelles, charges variables. Benchmark pack alterné3fois : médiane0.764327→0.677880s. Aucun gain production déclaré. Quatrième smoke structurelPASS mais wire5m médiane8740ms,p9549087ms,max61792ms,57.277%>5s. Ce cinquième smoke doit caractériser la capacité réelle après modifications démontrées, pas rechercher un PASS par répétition inchangée.

Après revue terminée uniquement : comparaison indépendante des replays complets/SHA, diagnostic exhaustif de latence parfeed. Distinguer temps prépersistance historique et coût réel des callbacks ; compteurs CPU quantifiés Windows et temps mural incluent scheduling. Ne pas réinterpréter PASS instrumentation comme validation statistiqueD6 ou capacité tempsréel. Aucun D6/PAPER, aucune collecte longue durant cette expérience. Aucun fichier DB historique modifié/supprimé.
