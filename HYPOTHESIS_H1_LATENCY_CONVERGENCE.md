# H1 — Convergence tardive / course de latence Binance → Polymarket

Statut : **hypothèse formalisée, non testée**. Aucun ordre réel ou paper n'a été
déclenché par ce document. Remplace l'hypothèse H_ARB (arbitrage de mispricing
UP+DOWN), invalidée par inspection directe de l'activité publique de Bonereaper
(coûts combinés UP+DOWN observés au-dessus de 100¢ dans la majorité des cas,
ex. 165,3¢, 144,5¢, 123,5¢ — incompatible avec un arbitrage sans risque).

## Origine

1. `analysis/bonereaper/d1_pairing_report.md` et `d2/d2_optimal_regime_report.md`
   montrent un edge brut qui varie fortement avec le délai de pairing (TimeToHedge),
   suggérant une composante de vitesse d'exécution.
2. L'activité publique récente (comptes "Gagné"/"Perdu", 26 septembre 2026) montre
   des entrées tardives dans la fenêtre 5 minutes, à des prix proches des extrêmes
   (ex. Up à 91,1¢, Down à 92,8¢, ou à l'inverse Up à 7,1¢, Down à 13,6¢) — cohérent
   avec un pari pris après que le prix BTC/ETH sous-jacent a déjà rendu une issue
   quasi certaine, mais avant que la cote Polymarket n'ait totalement convergé.
3. Cette activité n'est **pas** un échantillon représentatif (colonne filtrée sur
   les positions gagnantes) ; elle sert uniquement à motiver l'hypothèse, pas à
   la valider.

## Énoncé testable

Quand le prix BTC (ou ETH) évolue de façon à rendre une issue UP/DOWN nettement
plus probable, la cote du carnet Polymarket correspondant se resserre vers 0 ou 1
avec un délai mesurable (latence de re-cotation). Pendant ce délai, le prix affiché
est "périmé" (stale) par rapport à l'information déjà disponible côté Binance.

**H1** : Acheter le côté favorisé immédiatement après un mouvement BTC significatif,
au prix encore périmé affiché par Polymarket, produit un edge net positif après
frictions réalistes (spread, frais, échec de remplissage).

## Ce que H1 n'est PAS

- Ce n'est pas un arbitrage sans risque (contrairement à H_ARB) : le prix BTC peut
  encore se retourner avant expiration. C'est un pari directionnel à edge
  statistique, pas une position couverte.
- Ce n'est pas une preuve que Bonereaper fait exactement ceci — c'est l'explication
  la plus cohérente avec les deux observations disponibles, pas une certitude.

## Protocole de test (à respecter strictement)

1. **TRAIN** : calibrer le seuil de "mouvement BTC significatif" (en bps et en
   fenêtre de temps) et le modèle de juste-valeur proxy sur la première partition
   chronologique des données D5 uniquement.
2. **VALIDATION** : vérifier la stabilité du edge sur la deuxième partition, sans
   retoucher les paramètres.
3. **OOS** : ouvrir uniquement après gel complet de la règle. Aucun ajustement
   après lecture, conformément à `AUTONOMOUS_SUPERVISOR_PROTOCOL_20260920.md`.
4. Le dataset D5 actuel (3h02) est insuffisant pour une conclusion — cette
   première passe sert de **test de plausibilité** (le signal existe-t-il
   grossièrement dans les données déjà collectées ?), pas de validation.
   Une collecte prospective plus longue (plusieurs jours, régimes de volatilité
   variés) reste nécessaire avant toute conclusion.

## Frictions à modéliser (ne pas sous-estimer)

- Spread bid/ask réel au moment de l'achat, pas le midpoint.
- Latence de traitement + envoi d'ordre (le projet n'a pas encore mesuré sa
  propre latence de bout en bout vers Polymarket).
- Probabilité de non-remplissage si d'autres participants captent le même écart
  en premier (ce edge, s'il existe, est probablement disputé par d'autres bots).
- Risque de retournement du prix BTC avant expiration — ce n'est pas un edge
  garanti par trade, seulement en espérance sur un grand nombre de trades.

## Métrique de succès pour passer en VALIDATION

- Edge net moyen par trade > 0 après frictions modélisées de façon pessimiste
  (spread réel + friction actuelle 0,005/share + un délai d'exécution ajouté
  d'au moins 200-300ms pour simuler notre propre latence).
- Edge stable en signe sur au moins 3 sous-fenêtres temporelles distinctes du
  TRAIN (pas un résultat porté par une seule séquence de mouvement).
