# Chaîne accélérée — candidate, non lancée sur D5

Préparée le 20 septembre 2026 après demande de réduire fortement le délai. Aucun signal au PID 12408. Aucun changement de backend/app ou de la DB D5. 22 tests synthétiques PASS après validation du runner complet.

## Changements

1. Projection SQLite de métadonnées dans un NOUVEAU fichier metadata_projection.db du nouveau dossier de revue. Elle contient toutes les lignes et colonnes nécessaires aux contrôles SQL historiques, avec payload REJECT brut conservé. Les payloads BOOK et les ladders non utilisés par ces contrôles sont remplacés uniquement dans ce cache dérivé, JAMAIS dans la source. Aucun trigger/contrainte dans la projection ne peut masquer une anomalie par refus d’insertion. Comptage/progression par table et lots, cache 32 Mio.
2. audit_next travaille sur ce cache réduit, avec les prédicats historiques et comparaison intégrale sur fixtures.
3. quality.review original conserve integrity_check complet, foreign_key_check, anchors, expiration, couverture, gaps, provenance et seuils SUR LA DB ORIGINALE.
4. Deux replays distincts relisent la DB ORIGINALE. Pour la classe exacte NoTrade, le contexte inutilisé n’est plus alloué ; validation JSON BOOK et validation des ticks BTC conservées. Aucune stratégie arbitraire ne bénéficie de ce raccourci. Validation de l’identité BOOK, de l’ordre des événements, résolution et état comptable toujours exécutée.
5. Budget coopératif 3600 secondes, progression durable. Expiration = INCOMPLETE_TIME_BUDGET, jamais validation ni autorisation de recherche. Le budget peut dépasser légèrement en attente I/O non interruptible ; il n’est pas une garantie de réussite en une heure.

## Preuves / limites

22 tests PASS : schémas1/2, corruption, source inchangée, cache équivalent, chaîne complète avec deux replays, données JSON/BTC invalides, stratégie autre que NoTrade, contrôle de budget. Le benchmark REPLAY_BENCHMARK.json mesure 3301 événements synthétiques : 1,002 s référence / 0,439 s candidat initial, mêmes empreintes ; il précède l’ajout conservateur du contrôle BTC par tick. Aucun benchmark complet sur la production, aucun délai global promis.

La performance de construction/indexation de la projection et des PRAGMA sur 26 Go reste à mesurer. Le gain de replay seul ne prouve pas que recommencer ferait finir plus tôt. Le délai de l’audit historique est inconnu. L’ancien audit reste actif.

## Exécution possible seulement après autorisation et disparition confirmée du PID historique

Le runner refuse un lancement tant que PID12408 est vivant, ne l’arrête jamais lui-même, exige un nouveau dossier et un indicateur explicite. L’arrêt forcé de l’ancien audit n’est ni autorisé ni exécuté. Il faudra préserver son statut/logs, vérifier son identité avant toute action et l’absence effective après arrêt. Ne pas le qualifier d’arrêt propre : aucune annulation coopérative disponible dans ce processus.

Commande de nouvelle revue, À NE PAS EXÉCUTER AVANT AUTORISATION :

```powershell
Set-Location -LiteralPath 'C:\Users\Ramy\Documents\polymarket-crypto'
$reviewStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
& .\backend\.venv\Scripts\python.exe -B .\analysis\d5\auditor_next\run_accelerated.py --db 'C:\Users\Ramy\Documents\polymarket-crypto\data\d5_24h_20260920_085530\d5_live_24h_20260920_124822.db' --session '83b5cc8a-4592-4676-b28d-3da2ac6d0088' --out "C:\Users\Ramy\Documents\polymarket-crypto\analysis\d5\accelerated_review_$reviewStamp" --budget-seconds 3600 --execute-after-authorization
```

Cette commande n’est pas détachée ; si un lancement de fond est ensuite autorisé, utiliser CREATE_NO_WINDOW et conserver stdout/stderr dans un nouveau dossier. Mettre à jour la surveillance seulement après confirmation du nouveau PID. Ne pas supprimer les anciens rapports, bases, projections ou timestamps. Après expiration du budget : conserver les preuves et diagnostiquer, pas de lancement en boucle.
