# D5 — validation réseau réussie le 20 septembre 2026

Le blocage réseau observé à la reprise précédente est levé. La découverte des
marchés publics a réussi avec vérification TLS active ; aucun contournement ni
changement réseau n’a été effectué par cette exécution.

Le test réseau court D5 est VALIDÉ (`SMOKE_VALIDATED=true`, aucun motif d’échec).
Cela ne valide pas encore une collecte de 24 heures ni une stratégie.

## Exécution

- Dépôt exclusif : `C:\Users\Ramy\Documents\polymarket-crypto`.
- Nouvelle base : `data/d5_validation_20260920_083814.db`.
- Session : `a4b3d2f8-3eab-4c2f-8de4-03cf1d8fbd4a`.
- Commande depuis backend : `.\.venv\Scripts\python.exe -B run_d5.py --db ..\data\d5_validation_20260920_083814.db --seconds 340 --reconnect-after 20`.
- Mode SHADOW, stratégie NO_TRADE ; état final STOPPED.
- Durée enregistrée incluant initialisation/fermeture : 346,267 secondes.
- Aucune modification de code nécessaire pour cette nouvelle validation.

## Résultats

- 196 492 événements, dont 192 694 snapshots BOOK et 3 149 ticks BTC.
- Deux marchés 5m et un marché 15m ; rotation 5m observée.
- Deux reconnexions forcées, avec reprise des carnets sur les deux durées.
- Zéro mélange de marchés/tokens, événement accepté après expiration, carnet
  incomplet accepté, timestamp de disponibilité régressif ou ancre expirée ouverte.
- Aucun trou supérieur à 5 secondes au sein des marchés ; plus grand intervalle
  observé entre BOOK : 934 ms.
- Rejets enregistrés : 19 doublons, 312 carnets incomplets, 221 événements hors
  ordre, 82 événements post-expiration. Ces rejets ne sont pas des BOOK acceptés.
- Vérification SQLite : integrity_check=ok, zéro violation de clé étrangère,
  zéro ancre ouverte après arrêt.
- Deux replays offline NO_TRADE strictement identiques sur les 196 492 événements,
  résultats complets et empreinte du flux de décisions identiques :
  `252718387cea09746344e19409a07af1c5174b60f7ac360af89a2da89f3f3ca8`.
- Aucun ordre simulé ou réel, aucun fill, aucun inventaire ; capital simulé 500
  inchangé. Ces valeurs ne constituent pas une mesure de rentabilité.

## Limites restantes

`RESEARCH_ALLOWED=false` reste intentionnel : une collecte d’au moins 24 heures
et sa revue qualité séparée sont nécessaires avant la recherche. Aucun processus
de collecte n’a été laissé actif après le test.

Les moyennes réception moins timestamp source sont négatives : BOOK -339 ms,
BTC -312 ms (minimum BOOK -569 ms). Cela suggère un écart d’horloge à vérifier
avant toute étude de latence ; ces valeurs ne sont pas des latences réseau
physiques. Le seuil existant de 2 secondes n’est pas franchi. Aucune horloge
système n’a été modifiée.

## Preuves conservées

- `d5_validation_20260920_083814.log`
- `d5_validation_20260920_083814_audit.json` (audit CLI --require-smoke, code retour 0)
- `d5_validation_20260920_083814_replay.json`

Les rapports antérieurs et toutes les anciennes bases sont conservés. Aucun
ordre réel, passage en LIVE, accès à une clé privée ou transfert de fonds.
