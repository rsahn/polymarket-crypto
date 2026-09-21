# Profil complet de traitement — diagnostic technique

77 477 messages des captures publiques existantes, chronologie monotone conservée ; 77 436 BOOK et 41 REJECT. Nouvelle base technical_only.db. Aucun accès en écriture à une base de collecte, aucune recherche D6.

50.491 s de traitement pour 59.683 s de capture, soit 1534.47 messages/s. Parsing 1.205 s, normalisation 16.247 s, observer/store 28.743 s, commits 3.078 s. Le dernier flush et la boucle expliquent le solde. 118 commits, maximum 82.52 ms, 24 dépassent 50 ms.

L'observation/écriture domine (~57%), puis normalisation (~32%). CPU et temps mural des callbacks sont proches : la sérialisation et le travail CPU constituent une cible prioritaire. Sous Windows thread_time_ns est quantifié ; ne pas interpréter chaque petite différence CPU/mural ni sommer des écarts comme mesure précise d'I/O.

Limites : BTC et boucle réseau réels absents ; captures non contemporaines du smoke ; pas de test de disque froid ni de longue durée ; horloges de réception conservées pour le lot technique mais ce lot ne constitue pas une collecte prospective homologuée. Aucune causalité réseau définitivement établie. Le débit moyen ne prouve pas la tenue aux rafales. Le PASS d'instrumentation reste inchangé et aucun PASS de capacité n'est déclaré.

Prochaine cible : réduire le coût de sérialisation/persistance sans suppression de payload/profondeur/metadata et sans modification des horloges. Toute alternative doit conserver les valeurs/types requis, le replay, l'audit et une preuve d'équivalence sur ces mêmes captures avant nouvelle expérience prospective. Pas de relance inchangée.
