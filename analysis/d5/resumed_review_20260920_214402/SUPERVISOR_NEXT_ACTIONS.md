# Supervision autonome — prochaines verifications

Protocole prioritaire : analysis/AUTONOMOUS_SUPERVISOR_PROTOCOL_20260920.md.

1. Laisser finir la revue active (active_review.json). Aucun deuxieme audit ni lecture lourde concurrente. Observer telemetry.json / progress.json / logs et identity du PID. Une heure = alerte seulement.
2. A la sortie du processus, diagnostiquer les echecs d'outils et les corriger/tester/reprendre automatiquement. Ne pas transformer un timeout en defaut des donnees. Conserver tout resultat et ses hashes.
3. Avant toute acceptation definitive de la reutilisation de auditor_next PASS, executer UNE attestation complete de la source :
   backend\.venv\Scripts\python.exe -B analysis\d5\auditor_next\verify_source_provenance.py --review analysis\d5\resumed_review_20260920_214402 --reference analysis\d6\data_final_20260920\raw_manifest.json
   Le script refuse un audit vivant et un second hasher actif. Les empreintes code/source doivent correspondre. Hash attendu e4f7212036818141c86e2d45c0082adaa834126f61db3060c3809264c588d0bd. Aucune attestation PASS avant comparaison effective.
4. Lire FINAL_DATA_QUALITY_REPORT et REPLAY_1/2, verifier egalite complete et empreintes decisions/resultats, inertie NoTrade500. Conserver brut FAILED/KeyboardInterrupt. Qualifier l'arret avec COLLECTION_STOP/SESSION_END, ancres et integrite ; aucune modification de la source.
5. Completer en lecture seule les points demandes encore absents des rapports : regressions source acceptees par identite/generation et cote, gaps par feed/marche, evolution NTP brute avant/pendant/apres. Ne jamais corriger les timestamps. Documenter toute limitation de mesure.
6. Attention : AUDIT_NEXT_REPORT contient deja quelques gaps de carnet de 5 a 6,551 secondes. C'est un constat distinct du PASS smoke. Le gate strict >5s de quality.py reste en vigueur ; ne pas l'assouplir silencieusement. Attendre le rapport source complet pour le diagnostic de couverture/gaps.
7. Si un defaut reel des donnees ou une decision methodologique materielle bloque D5 : rapport complet, D5_DATA_QUALITY=FAIL, D6/Paper bloques, notifier la decision concrete necessaire ; pas de nouvelle collecte implicite.
8. Seulement apres D5 PASS + hashes/provenance valides : continuer D6 selon protocoles existants. OOS apres gel seulement, aucune selection apres OOS. Preparer jusqu'a PAPER500_READY_FOR_USER_APPROVAL, ne jamais demarrer Paper sans autorisation explicite.

Instrumentation complete sur http://127.0.0.1:8767/ : CPU/I/O/heartbeat toutes les 15s, etape/sous-etape/dernier avancement, PASS repris explicite, provenance SHA PENDING tant que non verifiee. Serveur superviseur independant ; aucun acces SQLite.

Tests : 29 tests de chaine passent ; 2 tests d'attestation supplementaires passent (equivalence SHA/code et mismatch, refus de hash simultane). Le probe de cache mesure des resultats identiques mais ne garantit aucun facteur de gain general a cause du cache OS.
`nMISE A JOUR : post_review_supervisor.py PID17852 attend PID14672 et executera automatiquement SHA source, complement timestamps et comparaison. Lire post_review_progress.json avant toute action. Ne pas lancer manuellement de hash/supplement pendant que ce helper est actif. Resultat attendu : SUPERVISOR_D5_VERDICT.json, a examiner avec toutes les preuves avant toute suite D6.
