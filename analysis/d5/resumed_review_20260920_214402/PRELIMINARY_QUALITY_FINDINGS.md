# Constats qualité intermédiaires — revue complète non terminée

Le replay 1 est en cours. Aucun verdict final complet et aucune autorisation D6/Paper ne sont délivrés.

## Gaps de réception

| Flux | Gaps > 5 s | Maximum | Couverture |
|---|---:|---:|---:|
| 5m | 10 | 8.557 s | 10943.628 s |
| 15m | 3 | 6.551 s | 10943.661 s |
| BTC | 2 | 5.457 s | 10942.580 s |

Ces interruptions observées dépassent le seuil inchangé de quality.py. Elles ne démontrent pas seules une perte de messages : inactivité du flux, reconnexion et rotation restent à distinguer. Elles imposent une revue méthodologique avant D6.

## Fermeture et structure

Le statut brut FAILED est conservé. Le contexte d’arrêt volontaire reste archivé ; COLLECTION_STOP=1, SESSION_END=3, anchors ouvertes=0, integrity_check=ok, foreign_key_check=[] confortent la fermeture physique. La règle inchangée signale toutefois UNCLEAN_STOP ; aucun statut n’est réécrit.

CROSS_MARKET_VIOLATIONS=0 ; POST_EXPIRY_ACCEPTED=0 ; MISSING_TOKEN_IDS=0 ; régressions de réception par flux=0. Les régressions des timestamps source acceptés seront vérifiées dans le complément.

Restent : deux replays complets et indépendants, égalité des états et hashes, SHA source complet, complément timestamps et comparaison des gaps, puis rapport final.
