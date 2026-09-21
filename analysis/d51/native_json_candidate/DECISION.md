# Sérialiseurs natifs — non intégrés

Trois candidats expérimentaux uniquement, dépendances isolées (rapports pip conservant versions, URLs et SHA), backend inchangé 835b1a419e783673db86432443c234a518225f0e8a4dfb19c6f71985872b5b3f.

Référence : full_stage_profile_20260921_141702, 77 477 messages en46.728s, observer/store28.510s.

- orjson3.12.0 avec validation récursive stricte : native_json_profile_20260921_142057,53.256s,observer/store34.940s. Aucun gain démontré.
- python-rapidjson1.25,mode natif strict listes : rapid_json_profile_20260921_142253,51.429s,observer/store33.180s. Tuples de profondeur refusés avant fallback json standard, coût supplémentaire démontré par test direct.
- python-rapidjson1.25 avec conversion contrôlée tuple→list : rapid_tuple_profile_20260921_142518,50.235s,observer/store30.418s. Aucun gain démontré ; normalisation également plus lente sur cette exécution, charges variables possibles. Ces essais uniques ne constituent pas une estimation statistique de régression.

Chaque candidat passe les3tests de types/Unicode/flottants/nonfinis/cycles. RapidJSON passe99936flottants finis aléatoires avec bits/type identiques après lectureJSON. Cela ne constitue PAS une preuve exhaustive de fidélité des DB : la comparaison des persistences/replays natifs n'a pas été exécutée faute de bénéfice de performance justifiant l'intégration.

Décision : aucune nouvelle dépendance dans backend/requirements.txt ou le venv ; aucun changement du format primaire, des audits ou des verdicts. Conserver les candidats et bases techniques, pas de suppression. Aucune collecte prospective lancée pour ces candidats.

Prochaine piste : éviter les sérialisations répétées de profondeurs identiques avec cache exact et borné, sans perte de payload et avec preuve d'équivalence. Le cache pickle antérieur n'avait pas de gain ; ne pas le réintroduire inchangé. Alternativement étudier le coût de construction des snapshots (BBO fourni remplaçant des extrema calculés) et l'architecture des rafales. Les optimisations doivent améliorer la capacité sans retimer ni abandonner des messages.

Documentation primaire consultée : https://github.com/ijl/orjson ; https://python-rapidjson.readthedocs.io/en/latest/dumps.html . Les mesures locales, non les benchmarks annoncés, déterminent cette décision.
