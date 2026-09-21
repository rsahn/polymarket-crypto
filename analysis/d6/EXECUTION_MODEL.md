# D6 — exécution future, spécification seulement

Aucun moteur réel ou PAPER/LIVE créé. Replay hors ligne seulement après validation et autorisation. Capital initial **500 USDC global** partagé entre tous les marchés simultanés ; pas 500 par slug, pas de remise à zéro après perte.

## Ledger causal

Décision à partir des seules features admissibles ; arrivée après latence fixée. Le fill utilise le carnet disponible à l'arrivée, jamais un instant sélectionné pour son résultat. Égalités : ordre déterministe conservateur documenté. Annulations et acknowledgements ont une latence.

Decimal pour monnaie/coûts ; ticks, minimums et arrondis explicites. À soumission réserver le pire coût autorisé + frais ; à chaque fill débiter immédiatement le cash total et diminuer la réserve correspondante (pas de double débit). Ordres concurrents partagent cash/réserves. Cash disponible et réservé >=0 à tout instant. Annulation libère uniquement le montant non dépensé ; aucun remboursement d'un fill défavorable. Pas de short non autorisé.

Chaque ligne : order_id/fill_id simulés, clés fortes, timestamps, budget de liquidité, cash, coût, frais et quantités. Conserver tous les legs non couverts et leurs coûts/risques. Inventaire d'un marché ne couvre pas celui d'un autre.

## Profondeur et non-double consommation

BUY sweepe asks croissants ; SELL bids décroissants, quantités partielles et rejets explicites. Un registre partagé entre ordres d'une politique interdit de consommer deux fois une share. Mondes contrefactuels indépendants ont des registres séparés.

Nouveau event_id ou snapshot ne signifie PAS nouvelle liquidité. Sans order IDs, snapshots répétés peuvent représenter les mêmes quotes. Modèle conservateur proposé : budget par token/niveau/épisode ; seule une augmentation de quantité observée crédite du renouvellement, diminution ne crée rien, budget plafonné au visible, consommation persistante. Reconnexion sans continuité ne remet pas le budget à neuf. Ce modèle peut sous-remplir ; il ne prouve pas le renouvellement réel. Toute variante moins conservatrice est déclarée et rapportée séparément, jamais sélectionnée sur OOS.

L'impact contrefactuel sur les autres participants reste inconnu. Plafonds de participation et stress préenregistrés ; ne pas inventer de profondeur ni importer un volume futur pour remplir le passé.

## Frais, latence, slippage, queue

Barèmes historiques par marché/token/date/rôle et arrondis sourcés. Prix*size séparé du cash avec frais. Rebates crédités seulement selon règle et disponibilité connues, jamais utilisés avant versement. Frais inconnus => pas de résultat net certifié, pas zéro par défaut.

Slippage ventilé : mouvement pendant latence, sweep en profondeur, frais séparés ; ne pas compter deux fois le spread payé. Latence mesurée ou grille de scénarios fixée avant résultat, tous publiés. Réception D5 ne mesure pas latence d'ordre de Bonereaper.

Maker : prix touché != fill. Sans queue/flow, pas de fill optimiste ; modèle principal non identifiable/non rempli jusqu'à hypothèse conservatrice testable. Pas de probabilité de fill ajustée sur OOS. Taker : sweep admissible à l'arrivée après latence.

## Merge et règlement

MERGE uniquement des shares complémentaires réellement détenues, paiement unique, coûts et délais explicités. Règlement uniquement sur événement de résolution confirmé selon règles/oracle, jamais à la simple échéance ou à l'aide d'un futur winner vu avant l'heure. Deux legs non atomiques. Positions non résolues conservées en fin de replay, cash réglé distinct de valeur liquidable prudente.

## Métriques futures obligatoires

| Métrique | Convention |
|---|---|
| Capital final, PnL, return % | Equity=cash+valeur liquidable nette ; résultat réglé séparé ; PnL=equity-500 ; return=100*PnL/500 |
| Max drawdown | Peak-to-trough de l'equity prudente, USDC et % ; prix absent => UNKNOWN/intervalle |
| Orders, fills, fill rate | Soumis/acceptés/rejetés/partiels ; nombre fills ; taux ordres avec fill et taux volumique séparés |
| UP/DOWN qty, paired qty, average pair cost | Par condition, agrégation sans appariement entre marchés |
| Directional residual / max exposure | Shares signées et risque USDC explicite ; pas compensation trompeuse entre marchés |
| Time unhedged | Temps avec résidu par marché et temps portefeuille exposé à au moins un résidu |
| Capital utilization | Réserve et coût investi / equity, moyenne temporelle/max, définitions séparées |
| Turnover | Notionnel BUY+SELL /500 ; merges/règlements séparés |
| PnL par marché, gagnants/perdants | Frais alloués explicitement, non résolus séparés |
| Concentration | Top1/5/10 du profit positif et part du PnL absolu ; net proche de zéro signalé |
| Frais, slippage, liquidité disponible | Totaux/distributions, participation, rejets de cash/profondeur, coût des legs manquants |

Les métriques doivent inclure effectifs, conventions, incertitudes et sensibilités. Aucun résultat économique calculé maintenant.
