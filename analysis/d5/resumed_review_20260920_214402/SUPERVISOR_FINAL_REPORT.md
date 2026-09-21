# Revue D5 complete : FAIL

D5_DATA_QUALITY = FAIL. D6_RESEARCH_ALLOWED=false. RESEARCH_ALLOWED=false. PAPER_STARTED=false.
Les huit etapes sont terminees, ainsi que les complements de provenance et timestamps. Le blocage porte sur l'admissibilite des donnees selon les criteres conserves, et non sur un timeout ou une corruption SQLite. Toute acceptation differente necessite une decision methodologique explicite. Aucun seuil n'a ete relache.

## Dataset et integrite

Prospective D5 short-window dataset : collecte effective **3 h 02 min 24,725 s**, jamais validation 24 h. Session du 20 septembre 2026, 10:48:27.267 a 13:51:02.122 UTC ; COLLECTION_STOP a 13:50:52.103 UTC. L'ecart inclut la fermeture de session.

Source : `C:\Users\Ramy\Documents\polymarket-crypto\data\d5_24h_20260920_085530\d5_live_24h_20260920_124822.db`. Taille logique 26 186 612 736 octets. SHA-256 complet : `e4f7212036818141c86e2d45c0082adaa834126f61db3060c3809264c588d0bd`. Source et timestamps inchanges ; lecture seule, WAL vide lors de l'attestation. Provenance du code PASS, schema 2 ; version `2b10856c9e4af10b68e71c38a39daa7c3a9d4516:working-tree-sha256:d217f12b9c6a2b2e130df454d25c42c434304b0f2ad1321fe669cab0759df1bc`.

| Controle | Resultat |
|---|---:|
| Evenements | 7 518 713 |
| BOOK / BTC | 7 441 212 / 66 517 |
| Cotes de carnet | 14 882 424 |
| Marches distincts 5m / 15m | 38 / 13 |
| Rotations 5m / 15m | 37 / 12 |
| Reconnexions Polymarket / Binance | 68 / 0 |
| WS_ERROR | 34 |
| CROSS_MARKET_VIOLATIONS | 0 |
| POST_EXPIRY_ACCEPTED | 0 |
| MISSING_TOKEN_IDS | 0 |
| Ancres ouvertes / expirees ouvertes | 0 / 0 |
| integrity_check complet | ok |
| foreign_key_check | aucune violation |
| Regressions de disponibilite / reception | 0 / 0 |
| Rejets totaux | 10 335 |
| OUT_OF_ORDER / INCOMPLETE_BOOK | 7 422 / 1 977 |
| DUPLICATE_EVENT / POST_EXPIRY_REJECT / CROSS_MARKET_REJECT | 683 / 252 / 1 |

## Gaps et couverture

| Feed | Evenements | Couverture s | Gaps >5s | Max ms | Somme des intervalles ms | Initial / final ms |
|---|---:|---:|---:|---:|---:|---:|
| 15m | 2842026 | 10943.661 | 3 | 6551 | 17677 | 919 / 256 |
| 5m | 4599186 | 10943.628 | 10 | 8557 | 63475 | 951 / 257 |
| BTC | 66517 | 10942.58 | 2 | 5457 | 10837 | 1903 / 353 |

Les 15 intervalles sont exhaustivement documentes dans GAP_DIAGNOSIS_FROM_REPORT.json/.md. Six correspondent a des transitions entre marches 5m, sept sont internes a un marche (4 en 5m, 3 en 15m), deux concernent BTC. Un silence de reception ne prouve pas a lui seul une perte de messages ; les causes de transport ne sont pas etablies. Ces depassements restent bloquants selon le seuil de 5 s conserve.

## Horodatage et horloge

Le scan complet de 14 948 941 lignes jointes couvre 7 507 729 evenements BOOK/BTC acceptes. Enveloppe BOOK : 744 reculs par rapport a l'observation precedente, 2 566 observations sous le maximum precedent, recul maximal 507 ms. Cotes BOOK (source et reception), BTC source et disponibilite : aucune regression. Les controles sont scopes par identite de marche et generation, puis cote/token pour les cotes.

Diagnostic borne des 100 premiers exemples : 98 sequences last_trade_price -> price_change et 2 last_trade_price -> book ; dans les 100, les timestamps des cotes et la disponibilite restent non decroissants. Le collecteur affecte a l'enveloppe le timestamp du dernier message, tandis que les cotes ont leur propre metadata. Cela explique les exemples inspectes ; ce sous-ensemble non aleatoire ne prouve pas le mecanisme pour tous les 744 cas. Le constat est conserve comme conflit de contrat d'horodatage a revoir, sans correction retrospective. Voir BOOK_ENVELOPE_REGRESSION_DIAGNOSIS.json et TIMESTAMP_SUPPLEMENT.json.

NTP : avant synchronisation environ 591-598 ms ; immediatement apres premiere synchronisation encore environ 591-598 ms. Le seuil initial 50 ms n'a pas ete atteint ; le passage a 100 ms a ete expressement autorise avant lancement. Maxima absolus Windows/Cloudflare : controles consecutifs 52,9522/53,6063 puis 57,0172/53,8729 ms ; avant collecte 53,4406/52,9242 ; durant 52,3967/58,8592 puis 69,6782/66,9141 puis 78,4449/78,8665 ; apres 78,3833/79,1627 ms. Les neuf fichiers bruts et leurs hashes sont verifies.

Limite importante : W32Time rapporte une derniere erreur de synchronisation 2 (donnees obsoletes), y compris au gate et ensuite. Les sondes discretes satisfont 100 ms mais ne prouvent ni une synchronisation Windows recente continue ni l'erreur d'horloge entre sondes. BOOK reception-source minimum -54 ms est compatible avec decalage entre horloges et asymetrie reseau ; attribution exacte par evenement non demontree. Moyenne BOOK 13 217,206 ms, maximum 158 514 ms ; BTC min 68, moyenne 597,428, max 4 346 ms. Aucun recalage applique.

## Fermeture

Statut brut FAILED/KeyboardInterrupt conserve. Arret volontaire autorise a environ 3 h ; COLLECTION_STOP=1, SESSION_END=3, ancres ouvertes=0, integrite et cles etrangeres PASS appuient une fermeture effective du writer. UNCLEAN_STOP resulte du statut brut du wrapper ; ce n'est pas une preuve de corruption. Aucune conversion retroactive vers STOPPED, aucune derogation implicite au gate.

L'ancien audit PID 12408 a ete abandonne explicitement : OLD_AUDIT_ABORTED_BY_USER_FOR_PERFORMANCE. Ses resultats partiels ne sont pas utilises pour valider. Les seules etapes reprises sont les etapes completes metadata/auditor_next de la nouvelle revue full_review_20260920_201805, avec hashes source/code/rapports verifies.

## Replays et etapes

Deux executions NoTrade independantes ont chacune traite 7 518 713 evenements et autant d'enregistrements de decisions dans le calcul d'empreinte. La liste decisions en memoire est vide par conception ; elle ne signifie pas absence de traces dans le hash. Etats et resultats complets identiques, 51 marches FLAT, capital initial/final 500, zero ordre/fill/inventaire. SHA des resultats recalcule independamment.

Replay 1 : decisions `6184bfe7562e14867bd18789f315bedd7d15d613662c1a948a13ef828d1cdaa7` ; resultats `00d76b967afeae5406afd09dabe1265550e6218f0bf67e13732a53c932ee9752`.

Replay 2 : decisions `6184bfe7562e14867bd18789f315bedd7d15d613662c1a948a13ef828d1cdaa7` ; resultats `00d76b967afeae5406afd09dabe1265550e6218f0bf67e13732a53c932ee9752`.

| Etape | Conclusion | Duree s |
|---|---|---:|
| 1 Metadata/provenance initiale | PASS repris et atteste | 1772,292 |
| 2 auditor_next complet | PASS repris et atteste | 800,862 |
| 3 integrity_check complet | PASS | 3395,439 |
| 4 foreign_key_check | PASS | 932,008 |
| 5 quality.py | mesures completes, anomalies presentes | 1801,390 |
| 6 Replay 1 | PASS | 3876,264 |
| 7 Replay 2 | PASS | 3373,239 |
| 8 Comparaison + gate | comparaison PASS, gate FAIL | inclus dans duree core |

Revue reprise : 3 h 42 min 58,527 s pour le core ; avec SHA source et complement timestamps, **13797.175 s, soit 3 h 49 min 57,175 s**, du 20 septembre 19:44:02.662870 UTC au 23:33:59.837389 UTC. Cette duree exclut la redaction finale. Les etapes reprises avaient coute 42 min 53,154 s dans la tentative precedente. Depuis le debut de cette nouvelle chaine a 18:18:05 UTC, delai mural total **5 h 15 min 54,837 s**, y compris timeout et reprise ; ce n'est pas le temps de l'ancien audit abandonne. Attestation SHA : 87,974 s ; supplement timestamps : 316,036 s. Les durees des etapes reprises ne doivent pas etre additionnees au delai mural comme si elles avaient ete reexecutees.

Les erreurs de supervision (remplacement atomique Windows et rendu des resultats SQLite) ont ete corrigees et 9 tests cibles ont passe, apres 29 tests de reference. Preuves preservees dans supervision_recovery_20260920_2244. Aucun bug de supervision restant ne justifie les gaps ou les regressions observees.

## Decision

D5_DATA_QUALITY=FAIL ; criteres non assouplis. Les motifs automatiques sont : ACCEPTED_TIMESTAMP_REGRESSION_BOOK_SOURCE, GAPS_REQUIRE_REVIEW_15m, GAPS_REQUIRE_REVIEW_5m, GAPS_REQUIRE_REVIEW_BTC, UNCLEAN_STOP. L'avertissement W32Time est egalement une limite explicite de la preuve d'horloge.

D6 et PAPER restent bloques. Aucune nouvelle analyse TRAIN/VALIDATION/OOS ni execution Paper dans cette revue. Les anciens travaux preparatoires D6 restent archives, sans homologation par cette revue. Le verdict D6 est INSUFFICIENT_DATA (dataset non admissible selon le gate actuel), pas une demonstration de NO_EDGE.

Recommandation pour la suite, non executee : definir explicitement avant toute nouvelle validation le contrat enveloppe/cotes, le traitement des silences aux rotations et les preuves de synchronisation requises, puis corriger/tester le collecteur pour une nouvelle collecte prospective. Accepter les observations actuelles sous un autre contrat serait une decision methodologique retrospective a tracer separement, jamais un effacement du FAIL actuel.

## Annexe : tous les marches

Les identites condition/token et generations sont dans DATA_QUALITY_REPORT.json. Couverture ci-dessous mesuree entre premiere et derniere reception, sans pretendre a une couverture continue.

| Slug | Snapshots | Couverture ms | Gaps >5s | Max gap ms |
|---|---:|---:|---:|---:|
| btc-updown-15m-1789901100 | 205176 | 691673 | 0 | 1149 |
| btc-updown-15m-1789902000 | 297965 | 897001 | 0 | 1899 |
| btc-updown-15m-1789902900 | 271998 | 896900 | 1 | 6551 |
| btc-updown-15m-1789903800 | 168086 | 899153 | 0 | 978 |
| btc-updown-15m-1789904700 | 258772 | 897106 | 0 | 1456 |
| btc-updown-15m-1789905600 | 291254 | 896463 | 0 | 1671 |
| btc-updown-15m-1789906500 | 168713 | 896753 | 1 | 6051 |
| btc-updown-15m-1789907400 | 296025 | 898181 | 0 | 1024 |
| btc-updown-15m-1789908300 | 198877 | 896464 | 0 | 1031 |
| btc-updown-15m-1789909200 | 185395 | 896271 | 1 | 5075 |
| btc-updown-15m-1789910100 | 220363 | 897570 | 0 | 1078 |
| btc-updown-15m-1789911000 | 203098 | 895558 | 0 | 1548 |
| btc-updown-15m-1789911900 | 76304 | 348728 | 0 | 1308 |
| btc-updown-5m-1789901100 | 49730 | 91781 | 0 | 3950 |
| btc-updown-5m-1789901400 | 135721 | 298143 | 0 | 753 |
| btc-updown-5m-1789901700 | 86673 | 298543 | 0 | 2297 |
| btc-updown-5m-1789902000 | 154302 | 297305 | 0 | 919 |
| btc-updown-5m-1789902300 | 124362 | 296136 | 1 | 5012 |
| btc-updown-5m-1789902600 | 120523 | 297632 | 1 | 5189 |
| btc-updown-5m-1789902900 | 99687 | 296796 | 1 | 5042 |
| btc-updown-5m-1789903200 | 85114 | 294348 | 1 | 5882 |
| btc-updown-5m-1789903500 | 104424 | 294428 | 0 | 2072 |
| btc-updown-5m-1789903800 | 95962 | 299121 | 0 | 844 |
| btc-updown-5m-1789904100 | 112945 | 291540 | 0 | 1135 |
| btc-updown-5m-1789904400 | 164177 | 299008 | 0 | 1273 |
| btc-updown-5m-1789904700 | 114621 | 297205 | 0 | 1166 |
| btc-updown-5m-1789905000 | 112779 | 297096 | 0 | 858 |
| btc-updown-5m-1789905300 | 93566 | 297397 | 0 | 4587 |
| btc-updown-5m-1789905600 | 110177 | 296265 | 0 | 1463 |
| btc-updown-5m-1789905900 | 95734 | 291669 | 0 | 972 |
| btc-updown-5m-1789906200 | 110897 | 292499 | 0 | 4309 |
| btc-updown-5m-1789906500 | 98891 | 296897 | 0 | 1436 |
| btc-updown-5m-1789906800 | 138199 | 298583 | 0 | 1040 |
| btc-updown-5m-1789907100 | 147431 | 298432 | 0 | 923 |
| btc-updown-5m-1789907400 | 135068 | 298065 | 0 | 1275 |
| btc-updown-5m-1789907700 | 151028 | 298047 | 0 | 880 |
| btc-updown-5m-1789908000 | 152212 | 298108 | 0 | 983 |
| btc-updown-5m-1789908300 | 124963 | 296574 | 0 | 1313 |
| btc-updown-5m-1789908600 | 107002 | 296758 | 0 | 1892 |
| btc-updown-5m-1789908900 | 187079 | 299293 | 0 | 774 |
| btc-updown-5m-1789909200 | 106793 | 296359 | 0 | 1112 |
| btc-updown-5m-1789909500 | 133331 | 298812 | 0 | 1380 |
| btc-updown-5m-1789909800 | 143533 | 298076 | 0 | 1139 |
| btc-updown-5m-1789910100 | 118149 | 297574 | 0 | 1123 |
| btc-updown-5m-1789910400 | 165410 | 297330 | 0 | 660 |
| btc-updown-5m-1789910700 | 137209 | 293946 | 0 | 4823 |
| btc-updown-5m-1789911000 | 93928 | 295714 | 0 | 3072 |
| btc-updown-5m-1789911300 | 185610 | 299174 | 0 | 1498 |
| btc-updown-5m-1789911600 | 103710 | 295270 | 0 | 1227 |
| btc-updown-5m-1789911900 | 175314 | 296905 | 0 | 1341 |
| btc-updown-5m-1789912200 | 22932 | 48253 | 0 | 552 |
