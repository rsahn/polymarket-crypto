# Décision anticipée — collecte D5 réduite à 3 heures

Le 20 septembre 2026, avant arrêt et avant résultats qualité, l'utilisateur demande : « vise 3 heures propres plutôt que d'attendre que le disque force l'arrêt vers 20–22 h. Ensuite audit → D6 → si les résultats passent les validations → Paper 500 ».

La cible devient 10 920 secondes d'acquisition (3 h 02, marge pour atteindre 3 h de couverture), arrêt vers 15 h 50 Paris. Ce changement ne valide pas le protocole initial de 24 h. Le nom de la base existante et ses timestamps restent inchangés. Aucun redémarrage, nouvelle base ou correction historique.

Méthode : Ctrl+C ciblé sur la console de PID 4920 et son lanceur 13112, après vérification stricte des identités et de tous les PID attachés. Test factice détaché réussi : asyncio exécute finally et reçoit KeyboardInterrupt. Le collecteur dispose d'une fermeture finally avec COLLECTION_STOP, SESSION_END et store.close ; le wrapper inscrit FAILED sur interruption. Ce statut sera conservé et expliqué, jamais transformé artificiellement en STOPPED.

Après disparition du writer uniquement : mesures NTP finales, audit read-only et deux replays NoTrade, dans analysis/d5/3h_20260920_124822_review. Critère durée 10 800 s ; tous les autres contrôles actuels restent actifs. Un éventuel UNCLEAN_STOP lié au statut brut demandera une revue explicite des preuves de fermeture ; aucune validation forcée. Les autres défauts/gaps ne sont pas effacés.

D6 et PAPER virtuel 500 sont autorisés conditionnellement aux validations précédentes. Pas de PAPER/LIVE maintenant ; jamais d'ordre réel, clé ou fonds. Aucun D6 automatique dans ce contrôleur. RESEARCH_ALLOWED reste false pendant collecte et revue. Aucun arrêt forcé si Ctrl+C échoue : signalement requis.
