# D5 — Reprise autorisee des controles manquants

Decision utilisateur : appliquer les optimisations proposees, tester leur equivalence, terminer la validation et remplacer la coupure automatique d'une heure par une alerte.

- Base source conservee, acces SQLite mode=ro et query_only=ON. Aucun VACUUM, checkpoint, schema, donnees ou timestamp historique modifie.
- Cache propre a chaque connexion de qualite/replay : 131072 Kio (128 Mio). Aucun changement persistant des parametres de la base ; mmap et temp_store non assouplis.
- Memoire libre mesuree avant lancement : environ 1,3 Gio. Cache borne ; connexions de replay successives, fermees independamment.
- 29 tests passes, dont comparaison integrale avec quality.review de reference, refus d'ecriture, reprise/provenance, alerte sans interruption, deux replays et resultats complets identiques sur fixtures.
- Probe source borne : analysis/d5/cache_probe_20260920_214309/BENCHMARK.json. Resultats identiques (118896 cotes, zero incoherence) pour cache 2000 Kio et 131072 Kio. Mediane 0,707 s / 0,422 s, mais le dernier passage petit cache est plus rapide (0,367 s) : effet du cache OS, aucun gain general garanti ni extrapolation du temps integrity_check.
- Seul le rapport auditor_next TERMINE PASS du dossier full_review_20260920_201805 est repris. Source/session/stat, hash quality.py, hashes acceleration.py/audit_next.py et etapes terminees controles ; empreintes des preuves consignees dans CARRIED_AUDIT_PROVENANCE.json. Aucun resultat partiel de PID12408 reutilise.
- Integrity_check est recommence integralement sur la source. Foreign_key_check, metriques/provenance quality.py, deux nouveaux replays NoTrade de la source et le quality gate seront executes dans ce dossier neuf.
- quality.py, ses seuils et ses criteres sont inchanges. Les statuts bruts FAILED/KeyboardInterrupt restent presents et peuvent faire echouer le gate.
- Une heure genere one_hour_alert=true ; aucun TimeoutError ni arret automatique sur duree dans ce pilote. Toute erreur reelle arrete la chaine et conserve le resultat.
- Aucun D6 supplementaire, Paper, LIVE, ordre reel, portefeuille ou transfert. RESEARCH_ALLOWED=false.
- Le compteur http://127.0.0.1:8767/ suit active_review.json. Le suivi de dix minutes ne lance pas d'autre revue et doit notifier fin/echec/alerte significative seulement.
