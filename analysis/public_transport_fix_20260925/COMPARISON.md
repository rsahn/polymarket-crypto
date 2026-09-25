# Différentiel transport HTTP — aucune sonde réseau Codex

| Élément | Requête manuelle décrite | Ancienne sonde | Correctif |
|---|---|---|---|
| User-Agent | Mozilla/5.0 explicite | défaut opener Python-urllib/3.13 constaté localement | Mozilla/5.0 explicite |
| Accept | non précisé dans le retour utilisateur | application/json | conservé |
| Redirect | urllib standard suit les redirections, sauf opener personnalisé non communiqué | NoRedirect rejette | conservé pour ne pas transférer les headers à une route hors allowlist |
| Proxy/environnement | découverte urllib standard si aucune personnalisation | build_opener utilise la même découverte standard | aucun override, aucune modification d'environnement |
| URL /time | https://clob.polymarket.com/time | base.rstrip('/') + /time, donc même URL | inchangé |
| Query /time | aucune | params absent => aucune, pas de '?' final | inchangé |
| Query Gamma public-only | limit=1 | urlencode({limit:1}) | /markets?limit=1 |
| Request | urllib.request.Request avec UA explicite | Request GET explicite, body=None, Accept explicite | seul UA ajouté |
| Opener | urlopen peut utiliser un opener global personnalisé; non documenté ici | nouveau build_opener(NoRedirect()) à chaque GET | inchangé |

Inspection hors réseau: handlers par défaut identiques sauf HTTPRedirectHandler remplacé par NoRedirect; addheaders standard Python-urllib/3.13. Aucune valeur de proxy enregistrée.

Le RED reproduit une réponse simulée 403 lorsque UA diffère de Mozilla/5.0, alors que la requête témoin réussit. Ce test démontre la différence de construction et le correctif; il ne prouve pas encore que le serveur réel filtre uniquement le User-Agent. Les autres différences sont conservées et documentées plutôt que modifiées simultanément. Le nouveau rapport local permettra de confirmer ou réfuter cette hypothèse.

public-only: aucun chargement .env/credentials/wallet, aucune dépendance à la version du SDK pour les GET publics; flags du processus seulement. Trois routes exactes. Rapport horodaté créé exclusivement, ancien rapport jamais écrasé. Aucun POST, ordre, annulation, signature, déploiement, proxy/VPN ou transport monétaire. BTC V1 inchangée.
