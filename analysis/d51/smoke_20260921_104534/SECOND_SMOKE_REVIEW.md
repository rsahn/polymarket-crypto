# Deuxième smoke D5.1 — verdict FAIL immuable

**D51_DATA_QUALITY = FAIL.** D5 historique et premier smoke restent FAIL séparément. Aucun D6 ni Paper lancé,aucun timestamp/source modifié.

Collecte SHADOW/NO_TRADE500 de1321,822s (~22min01,8s),STOPPED.818688événements :776312BOOK,41548BTC ;5marchés5m,2marchés15m ;5rotations (4×5m,1×15m).5tentatives réseau,10marqueursRECONNECT,5WS_ERROR.743rejets :677horsordre,64doublons,1cross-market,1expiré. Cross-market accepté0,post-expiry accepté0,missingtokens0,ancres ouvertes0. SQLite integrity=ok,FK=0. Code/provenance inchangés. Capital500,zéroordre/fill/inventaire.

## Défauts conservés

- ACCEPTED_AFTER_COLLECTION_STOP :202BOOK15m,IDs818483–818685 (intervalle avec contrôles),réception du1789981695750 au1789981696536,aprèsmarqueurID818482 à1789981695748.
- RECONNECT_GAP_OVER_5S :2gaps5m,5134ms et7622ms. Les5transitions ont des preuves et respectent le protocole prospectif ; elles ne sont pas masquées. Aucun gap>5s15m/BTC.
- RECEIVE_CLOCK_REGRESSION :1signal produit par SHUTDOWN_GAP=-788ms,car ledernierBOOK15m est post-stop. Les séquences de réception desfeeds ont0régression dans le rapport ; ne pas présenter ce libellé comme un reculWindows/NTP prouvé.

Toutes7sériesNTP (2avant,4pendant,1après) PASS,offsetabsolumax14,164ms. La correctionW32Time64s a tenu sur cette observation, sans garantir une stabilité future illimitée.

## Replays

Deux replays complets818688événements, résultats et états inclus identiques, comparaison indépendante et SHA résultats recalculés.

- décisions, replay1 **et** replay2 : `0d4eff77e110a0bdf69aae33dc642aca0bab39e2cae646b07e493f5f2fe8cf74`
- résultats, replay1 **et** replay2 : `8b4eb7aaee38b40ebb4e173a0cf1655cdd8779fea84f6d021a1eb787d9f001ba`
- source : `bd81583fc431846c8ce1140c364dbfb1f62b884d6df90b3b2e4e081fc2f90d3f`,statinchangé.

Revue8étapes :1662,475s ;jusqu'austatutfinalaprèsSHA :1666,214s (~27min46s depuispremièreémissionprogress). PID8428 terminé,aucun doublon.

## Diagnostic et travaux suivants autorisés

BOUNDED_READONLY_DIAGNOSIS.json utilise uniquement unetail512événements et25IDs tousles100000,avecSQLite mode=ro&immutable=1. Il confirme les202BOOK tardifs. Sur193BOOKéchantillonnés,le retardwire égale le retardétat,pouvantatteindre107s5m et193s15m :ce n'est donc pas seulement un étatinchangé dans cetéchantillon. Ce résultat ne prouve pas encore le lieu du backlog.

Reproduire synthétiquement la course de callbacks pendantannulation et poser une barrière globale avantCOLLECTION_STOP si confirmée. Profiler le chemin de traitement : live.on_book appelleBTCFeatures.at pour chaqueBOOK alorsque sesfeatures ne sont persistées parObserver que lorsdesancres (auplusunefoisparsecondeparmarché). Réduire ce calcul redondant seulement avec tests d'équivalence chronologique et mesure ; conservertousévénements/timestamps/profondeurs. Examiner reconnexions etlatence aprèscorrectif,dansuneNOUVELLEexpérience. Aucun seuilrelâché ni simple relance inchangée pour obtenirPASS.

Preuves : review/D51_FINAL_REPORT.json,D51_SUPPLEMENT.json,INDEPENDENT_REPLAY_COMPARISON.json,NTP_POST_COLLECTION_SUMMARY.json,BOUNDED_READONLY_DIAGNOSIS.json ;codeoriginalarchivé avantcollecte dans prepared_smoke2_20260921_1035.
