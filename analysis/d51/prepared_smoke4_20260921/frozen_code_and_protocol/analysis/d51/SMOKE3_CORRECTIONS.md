# Troisième smoke — corrections préalables, critères inchangés

Le deuxième smoke reste FAIL. Aucune base passée ni timestamp modifié. La revue était terminée et le processus absent avant ces changements.

1. Une fixture concurrente reproduit BOOK et BTC acceptés après COLLECTION_STOP lors d'un arrêt demandé et d'un timeout (stop_fence_before_fix.log,2échecs). Barrière globale synchrone posée AVANT le marqueur : tout callback tardif est enregistré REJECT/COLLECTION_STOP_FENCE avec son contenu brut et sa réception d'origine. Fermeture/ancres/SQLite restent contrôlées. Les4tests d'arrêt passent après correctif.
2. BTCFeatures.at était évalué pour chaque BOOK, alors que seules les ancres utilisent cette valeur. Observer accepte désormais un fournisseur évalué seulement à la création d'une ancre ; l'heure d'observation est capturée avant l'appel et reste figée. Aucun BOOK, tick, profondeur ou message n'est écarté. Les sorties complètes BOOK et features d'ancres sont égales à la référence eager sur fixture causale incluant des ticks futurs.
3. Profil synthétique mêmefixture2000BOOK/1800ticksBTC/20niveaux : appelsfeatures2000→2,4ancresidentiques SHA2937c0372849663fc5c3ee351fc0eef14d9406299d3f2f2f3e15fd41eb7970b6 ;2,185s→1,471s sousprofilage (~1,49x). Ce résultat ne garantit ni ce gain enréel ni disparition des déconnexions. Preuves perf_20260921.
4. Statut léger ajoute parfeed compte/moyenne calculable/max/dernier retard wire et dernier délai de traitement, sans correction d'horloge ni filtre de données.

Toute la suite :182testsPASS, TEST_RESULTS_BEFORE_SMOKE3.json. Nouveau smoke1320s SHADOW/NO_TRADE500 aprèsdoublegateNTPfrais. W32Time64s inchangé. Aucun seuil modifié, aucune panne artificielle. Audit8étapes etdoubleNoTrade automatiques aprèsfermeture. SiFAIL, conserver lespreuves etdiagnostiquer ; aucunD6/Paper surdataset nonadmissible.
