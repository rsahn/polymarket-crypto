# Index de doublons conservé — mesure technique

L'index set accompagne la deque bornée à 2048 empreintes distinctes acceptées. Même éviction, aucun rafraîchissement sur rejet, reset commun à chaque connexion. Le remplacement supprime la recherche linéaire sans modifier les règles de données.

184 tests PASS (TEST_RESULTS_DUPLICATE_INDEX_20260921.json). 77 477 snapshots identiques à la référence figée (raw_probe_20260921_125200/normalization_equivalence_duplicate_index.json). Comparaison persistée exhaustive PASS : 77 479 événements, 154 872 côtés, 236 ancres, 2 marchés. Seuls session_id et closed_at_ms de fermeture technique, propres à chaque exécution, sont exclus ; timestamps d'événements, payloads et profondeurs identiques.

Même lot complet : 50.491 -> 46.728 s ; 1534.47 -> 1658.04 messages/s (+8.05%). Normalisation 16.247 -> 12.792 s (-21.27%). Observer/store 28.743 -> 28.510 s. Mesures séquentielles uniques, pas une estimation statistique ni preuve de capacité en production. Aucune nouvelle collecte lancée sur ce seul gain.

Optimisation conservée ; cible suivante : coût de sérialisation/persistance qui reste dominant. Les compteurs mur/CPU seront conservés dans la prochaine expérience prospective. Le FAIL D5 historique et les PASS/FAIL D5.1 précédents restent inchangés ; aucune base historique modifiée ; aucun D6 ou PAPER.
