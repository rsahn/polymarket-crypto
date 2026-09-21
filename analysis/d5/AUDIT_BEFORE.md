# D5 — audit avant modification fonctionnelle

Le dépôt et ses modifications locales ont été inventoriés. Les empreintes des
fichiers préexistants et le diff backend initial sont conservés à côté de cette note.

Le bug est dans `C3ShadowObserver.observe` : `anchors[market_key]` réutilise la
file « 5m » après rotation. `_persist(anchor, now, second)` ne reçoit ni slug,
ni condition, ni token du snapshot de hedge. `last_anchor_ms` et `seen` ont le
même problème d'identité. Aucun événement ne clôture les ancres lors d'une rotation.

`main.run_market_session` possède déjà les métadonnées immuables et protège les
callbacks par génération ; `on_rotated_quote` ajoute slug/condition au snapshot.
`PolymarketOrderbookCollector` possède les deux tokens, les niveaux et l'expiration,
mais expose surtout le meilleur prix. `_reset_connection_state` oublie de vider
les indications `_authoritative_top`. Les mises à jour ne filtrent pas encore
les événements source retardés par token. Les tests de normalisation comprennent
un ancien format synthétique non pris en charge et une assertion `stale_token`
que le collector ne fournit plus : adapter ces tests au vrai protocole, sans
inventer un carnet depuis un ancien format de dashboard.

`Database.poly_quotes` et `PaperAudit` utilisent la durée comme `market_id`.
`PaperExecutor` simule déjà des achats en shares, mais ne fournit pas de replay
global, de ventes ou de résolution de l'inventaire directionnel. Ces interfaces
historiques sont conservées pour l'audit.

Modifications prévues :

- durcir C3 à la source et désactiver son écriture historique dans le point
  d'entrée live ; aucune migration des anciennes bases ;
- conserver les transports Binance/Polymarket et la découverte ; ajouter
  métadonnées, profondeur, horodatage par token, resets et rejets explicites ;
- introduire `app/d5/` : identité immuable, base versionnée, session SHADOW,
  ancres persistées à T0, lifecycle, runner borné et audit ;
- replay indépendant et déterministe avec une stratégie de test non rentable
  par hypothèse, positions en shares, ventes possibles, frais configurables,
  et résidu non résolu lorsque l'issue réelle est absente ;
- tests synthétiques A/B, rotation, tokens, expiration, ordre, doublons,
  reconnexion, comptabilité, déterminisme et absence de look-ahead ;
- test réseau court uniquement après réussite des tests, puis audit. Aucune
  recherche D5 sur les anciennes données ou sur les premières minutes.
