# Décision méthodologique avant collecte D5 24 h

Le critère initial de 50 ms sur tous les échantillons de deux contrôles consécutifs
n’a pas été atteint. Certaines mesures isolées étaient inférieures à 50 ms,
mais cela ne validait pas ce critère. Aucune collecte de production n’avait démarré.

Sur autorisation explicite de l’utilisateur, le maximum absolu est porté à
100 ms inclus, sur chacune des trois mesures de chaque référence NTP, pendant
deux contrôles consécutifs espacés d’environ une minute. W32Time doit rester
actif, la source NTP confirmée, tous les tests réussis et au moins 120 Gio libres.

Cette décision est prise et enregistrée AVANT le lancement prospectif. Les
mesures et le statut du gate précédent sont conservés ; elles ne sont pas
reclassées sous le nouveau seuil. Deux nouveaux contrôles sont requis.

Tous les timestamps source/réception restent bruts ; aucun recalage, correction,
réécriture historique ou correction a posteriori. Mesures NTP conservées avant,
pendant et après la collecte. SHADOW / NO_TRADE, capital virtuel 500 ; aucun
ordre, fill, inventaire, passage PAPER/LIVE ou D5 Research.
