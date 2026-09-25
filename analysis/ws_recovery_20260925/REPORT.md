# Qualification D6 — checkpoint du 25 septembre 2026, 18:57 UTC

## Verdict

PAS ENCORE PRÊT POUR LE LIVE. Progrès démontré : récupération WS après une régression réelle, sans accepter le message ancien ni changer les timestamps. Le blocage principal du dernier diagnostic est la complétude après C, pas la fraîcheur.

## Changements de cette étape

- Nouveau backend/app/live/ws_recovery.py : au maximum deux reconnexions après régression ou panne réseau/timeout, délai 250 ms entre tentatives, fermeture avant nouvelle génération, arrêt à expiration, propagation de l'annulation et conservation de la preuve de régression expurgée. Une erreur d'identité ou de schéma n'est pas contournée.
- Intégration uniquement dans le diagnostic --health-contract de analysis/qualify_post_genesis.py. Aucun changement du parseur WS, de fixed-C, de Genesis ou de BTC V1.
- Dix cas de test WS : snapshots et deltas régressifs, absence de disponibilité avec un seul nouveau snapshot, fermeture, annulation pendant lecture ou attente, nombre de tentatives borné, identité, expiration et paramètres invalides.
- Deux cas supplémentaires d'exécution simulée : timeout après envoi ambigu et interruption locale pendant soumission. Le journal reste RECOVERY_REQUIRED, sans nouvel envoi automatique.

## Mesures réelles

Rapport : D6_POST_GENESIS_READINESS_20260925_185735_044830.json.

| Mesure | Avant : 18:46:07 | Après : 18:57:35 |
|---|---:|---:|
| Âge inventaire | 1255 ms | 475 ms |
| Âge account | 556 ms | 257 ms |
| Âge carnet | indisponible | 75 ms |
| WS | BOOK_REGRESSION, déconnecté | SYNCHRONIZED |
| Reprise scan / génération | 0 / 0 ms | 0 / 0 ms |
| SYSTEM_READY | false | false |

Le nouveau run contient une régression price_change de -2 ms en génération 1. Le lecteur la rejette, ferme la connexion puis se resynchronise dans une génération suivante. MARKET_ELIGIBLE_NOW=true à l'évaluation. La preuve de régression reste dans diagnostics.recovery.attempts. Le statut RUNNING du rapport décrit le lecteur à l'évaluation, avant son annulation normale en fin de diagnostic.

L'amélioration des temps RPC entre les deux runs n'est PAS attribuée à la reconnexion WS : ces appels varient et ce n'est pas une expérience contrôlée sur le fournisseur. Une récupération observée ne prouve pas la fiabilité à long terme. La fermeture de la première connexion a pris environ 2 s, hors âge de la génération finale ; le temps de remise en service doit rester mesuré.

## Vérification

RED : import du nouveau module inexistant, test de récupération en échec avant implémentation.
GREEN ciblé puis suite complète. Première suite : deux incompatibilités avec un lecteur injecté dont run() n'accepte pas connect_factory ; corrigées sans affaiblir les assertions. Suite finale : 737 passed, 25 subtests passed, 3 avertissements DuckDB existants, 45,35 s. Zéro appel SDK monétaire et zéro connexion externe tentée par la suite ; 16 méthodes SDK protégées.

Audit : 117 fichiers, AUDIT_OK, appels monétaires verrouillés. Dernier run : flags false, submit_allowed=false, Genesis inchangé. Le seuil 500 ms et l'ordre account puis rechecks B/C sont conservés. Pas de modification du contrôleur monétaire.

## Travail restant, ordre proposé

1. **Preuve post-C.** Reconstituer précisément les exigences du contrat et les garanties disponibles. Le validateur actuel prouve la couverture jusqu'à C et garde current_inventory_proven=false. Le flux utilisateur documente les ordres/trades authentifiés mais ne fournit pas, dans la page examinée, une barrière commune attestant la complétude CTF/account/indexer. Source officielle examinée : https://docs.polymarket.com/trading/realtime-order-updates . Cela ne prouve pas qu'aucune autre source ne peut convenir. Ne pas substituer un timestamp récent à une preuve de couverture.
2. **Qualification prospective du WS et des seuils.** Préparer une capture bornée et un replay conservant temps source/réception, séquences et profondeur. Définir le protocole avant les résultats. Comparer les budgets de fraîcheur séparément des délais d'exécution. Les rapports synthétiques seuls ne permettent pas de justifier 1500 ms ou d'évaluer la stratégie ; ne pas présenter la simple comparaison des âges comme un backtest. Examiner les captures déjà qualifiées et ne pas réutiliser un OOS pour sélectionner le seuil.
3. **Cycle complet.** Les incidents ciblés sont testés avec faux transport. Il reste à relier les preuves de cash/frais/réservations et d'inventaire au runner réellement destiné à être utilisé, puis à définir les opérations d'arrêt/reprise. Aucun test SDK monétaire réel autorisé.
4. **Décisions finales.** Le budget et les limites de perte du pilote ne sont pas autorisés par les valeurs par défaut. Les faire décider une fois le dossier technique concret. Ne pas armer automatiquement.

## Suivi

Automatisation de cette tâche : qualification-d6-avant-live, active, toutes les 30 minutes. Continuer les étapes utiles, signaler seulement progrès significatif, panne, décision nécessaire ou qualification complète. Ne pas répéter les runs sans hypothèse ni altérer les critères pour forcer un verdict. Une autre automatisation historique D5 existe dans une autre tâche : préserver ses travaux et éviter les charges lourdes concurrentes.

Le PC doit rester allumé et l'application ouverte pour le travail local planifié : https://learn.chatgpt.com/docs/automations?surface=app .

## Prochain run cible, si utile pour une nouvelle hypothèse

```powershell
$env:REAL_ORDERS_ENABLED = 'false'
$env:LIVE_EXECUTION_ARMED = 'false'
$ancienRpc = $env:POLYGON_ARCHIVE_RPC_URL
try {
    $env:POLYGON_ARCHIVE_RPC_URL = 'https://polygon.drpc.org'
    python 'C:\Users\Ramy\Documents\polymarket-crypto\analysis\qualify_post_genesis.py' --target-machine --health-contract --diagnostics
} finally {
    $env:POLYGON_ARCHIVE_RPC_URL = $ancienRpc
}
```

Pas de relance manuelle nécessaire pour ce checkpoint : le run ci-dessus a déjà été mesuré.
