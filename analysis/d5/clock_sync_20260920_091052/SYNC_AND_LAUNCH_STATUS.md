# Windows Time — synchronisation autorisée et lancement conditionnel D5

Mise à jour du 20 septembre 2026.

## Actions et mesures

- Mesures avant synchronisation conservées dans `before.json` :
  time.windows.com +0,5905412 à +0,5918426 s ;
  time.cloudflare.com +0,5957746 à +0,5982869 s.
- Service W32Time démarré avec élévation UAC après autorisation explicite.
- Deux commandes normales `w32tm /resync` réussies (code 0) :
  synchronisations Windows déclarées à 09:11:31 et 09:12:49 locales.
- W32Time Running ; source time.windows.com,0x9 ; stratum 5 ; indicateur de
  dérive 0 et dernière erreur de synchronisation 0.
- Le relevé immédiat `after_initial.json` reste proche de +0,59 s : le succès
  de la commande ne signifie pas que la correction progressive est terminée.
- Six demandes `/resync /soft` ont été journalisées ; Windows les a refusées
  pour données obsolètes. Elles ne sont pas présentées comme des synchronisations
  supplémentaires réussies. Le service poursuit sa correction normale.
- Au premier contrôle du superviseur, médianes :
  time.windows.com 0.5495232 s ;
  time.cloudflare.com 0.5561007 s.
  L’écart diminue, mais le critère de départ n’est pas encore atteint.

Configuration observée, non modifiée : MaxAllowedPhaseOffset=1 seconde,
PhaseCorrectRate=1, UpdateInterval=360000, SpecialPollInterval=32768 secondes.
Microsoft indique qu’en dessous du seuil MaxAllowedPhaseOffset, Windows ajuste
progressivement la fréquence d’horloge. Cette configuration et la baisse des
mesures sont cohérentes avec une correction progressive du retard local.

Source : https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings

Le retard local d’environ 0,59 s reste l’explication probable des deltas
source/réception négatifs du smoke. Le délai réseau et l’écart d’horloge source
contribuent également à ces différences ; aucune valeur historique n’est corrigée,
réécrite, décalée ou reconstruite. Aucune configuration NTP, clé de registre,
fuseau horaire ou heure manuelle n’a été modifiée.

## Lancement autonome armé, collecte pas encore démarrée

`backend/start_d5_24h_when_synced.py` fonctionne en processus détaché.
PID réel initial : 16280. État : `launch_gate_status.json`.

Il mesure les deux références chaque minute. Conditions cumulatives de lancement :

1. W32Time Running et source Windows NTP confirmée.
2. Trois offsets par référence, chacun en valeur absolue <=50 ms.
3. Deux contrôles consécutifs réussis.
4. Code applicatif inchangé depuis le préflight ; les 45 tests sont réexécutés
   avant le lancement et doivent réussir.
5. Au moins 120 Gio libres au lancement selon le budget de stockage préparé.

Les 50 ms constituent un critère opérationnel conservateur de ce protocole,
pas une garantie universelle d’exactitude de Windows ni de latence réseau.
Les conditions du lancement ont été vérifiées sur six cas synthétiques.

Après convergence, il crée exclusivement une nouvelle base :
`data/d5_24h_20260920_085530/d5_live_24h_YYYYMMDD_HHMMSS.db`.
Le timestamp du nom sera celui du lancement effectif. Le répertoire de rapports
sera `analysis/d5/24h_YYYYMMDD_HHMMSS` et sera indiqué dans le statut du superviseur.
Aucune base 24 h n’est créée avant la validation de l’horloge.

La collecte dure 86 520 secondes (24 h 2 min), en SHADOW / NO_TRADE avec capital
virtuel 500, aucun ordre/fill/inventaire. Le superviseur arrête proprement puis
exécute uniquement le DATA QUALITY REPORT et deux replays déterministes NoTrade.
RESEARCH_ALLOWED reste false ; aucun D5 Research n’est lancé.

L’attente d’horloge est bornée à quatre heures. Si la convergence échoue, aucun
collecteur n’est lancé et le blocage est signalé. L’ordinateur doit rester allumé
et alimenté ; une demande temporaire de maintien d’éveil est active.

Automatisation de suivi créée : `d5-surveillance-collecte-24-h`, contrôle horaire
dans cette tâche, silencieux sans changement significatif. Elle signale démarrage
réel, panne, fin ou décision requise ; elle ne lance aucun deuxième collecteur.

## Preuves

- before.json ; after_initial.json ; convergence_*.json
- windows_sync_transcript.txt ; sync_result.json
- windows_sync_followup.txt ; followup_result.json
- windows_sync_convergence.txt
- preflight_tests.log : 45 tests réussis
- launch_gate_status.json et launch_gate_stdout/stderr.log

Les mesures NTP continuent d’être conservées avant le lancement et pendant/après
la collecte, dans des fichiers distincts des données de marché.
