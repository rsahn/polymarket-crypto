# Constats intermédiaires — ne remplace pas le verdict final

La revue PID8428 est active. Aucun audit/replay supplémentaire, modification backend/runner/HEAD ou écriture source. Attendre D51_FINAL_REPORT.json.

Sources : review/DATA_QUALITY_REPORT.json, AUDIT_NEXT_REPORT.json, stdout du lanceur, inspection statique de live.py. NTP_POST_COLLECTION_SUMMARY.json : toutes les séries passent.

## Données établies par les rapports existants

818 688 événements,776 312 BOOK,41 548 BTC ;5 marchés5m,2 marchés15m ;4 rotations5m et1 rotation15m. Cross-market accepté0,post-expiry accepté0,missing tokens0,ancres ouvertes0. Rejets743 :677 horsordre,64 doublons,1 cross-market,1 expiré. Code inchangé. SQLite integrity et FK PASS.

Gaps5m >5s :
- 1789980599824 →1789980607773 :7 949ms, autour d'une frontière5m ; vérifier preuve de transition avant classification.
- 1789980884192 →1789980889326 :5 134ms, intérieur de la fenêtre ; classification/reconnexion à confirmer.
- 1789981499265 →1789981506394 :7 129ms, autour d'une frontière5m ; vérifier preuve de transition.
- 1789981636390 →1789981644012 :7 622ms, intérieur de la fenêtre ; classification/reconnexion à confirmer.
Aucun gap>5s15m/BTC. Les5 erreurs WebSocket visibles dans stdout indiquent « no close frame received or sent » : ce texte ne prouve pas leur cause réseau/serveur/local.

Ancienneté BOOK source moyenne~94 129ms,max227 892ms ; elle concerne le temps de l'état composite, pas nécessairement le dernier message wire. Diagnostic requis après revue : comparer wire/source côté/réception pour séparer état inchangé et retard de transport/traitement. Ne pas inventer une cause CPU à partir de cette seule métrique.

## Fermeture : anomalie candidate à confirmer par le supplément

Le rapport place le dernier BOOK15m à1789981696536, après le COLLECTION_STOP utilisé par les bornes (1789981695748). Le clamp trailing_gap=0 du rendu historique ne prouve pas l'absence d'événement post-stop. Le nouveau supplément contrôle explicitement ce cas et doit fournir les événements/counters.

Inspection statique : live.run écrit COLLECTION_STOP puis annule les tâches parents ; les collectors enfants sont annulés dans les finally de market_loop, après invalidation locale de chaque génération. Un enfant déjà prêt peut potentiellement exécuter son callback avant que son parent ne soit repris pour annulation. C'est une hypothèse de course à reproduire synthétiquement après fin de la revue, pas une justification pour modifier la donnée ni le critère. Une correction candidate serait une barrière globale de callbacks posée avant le marqueur d'arrêt, avec conservation explicite des rejets tardifs et tests BOOK/BTC.

Aucun de ces constats ne vaut PASS. Conserver tous les résultats ; diagnostic et correction éventuelle uniquement après clôture de la chaîne actuelle.
