# D5 — reprise de l’instrumentation, 20 septembre 2026

> Mise à jour : le nouveau test réseau est réussi. Voir [VALIDATION_RESEAU_20260920.md](VALIDATION_RESEAU_20260920.md). Le blocage décrit ci-dessous est historique.

Dépôt utilisé : `C:\Users\Ramy\Documents\polymarket-crypto`.

Les corrections ci-dessous sont validées par les tests locaux. La validation sur
les flux publics Polymarket reste BLOQUÉE par la résolution DNS observée ; D5 ne
peut pas être déclaré entièrement validé. Aucune recherche ni optimisation de
stratégie n’a été effectuée.

## Corrections de cette reprise

- `backend/app/d5/features.py` : le prix de référence d’un rendement BTC doit
  avoir ses trois horodatages (disponibilité, réception, source si présent) au
  plus tard à la borne passée. Un timestamp source ultérieur à cette borne ne
  peut plus contaminer le rendement.
- `backend/app/d5/store.py` et `observer.py` : contrôle de l’expiration sur
  l’enveloppe, chaque côté du carnet et la disponibilité effective monotone.
  Rejet avant insertion du BOOK, sans laisser un événement partiellement écrit
  lorsque l’horloge a déjà dépassé l’expiration. Les contrôles d’identité et
  d’expiration à l’entrée de Store.book restent actifs sous `python -O`.
- `backend/app/d5/audit.py` : détection des BOOK sans leurs deux côtés et des
  timestamps de côtés après expiration. Ces anomalies empêchent la validation.
  L’export exige un nouveau fichier et utilise une création exclusive : ni la
  base ni un rapport existant ne peuvent être écrasés par `--out`.
- `backend/tests/test_d5_integrity.py` : neuf nouveaux tests, dont un scénario
  synthétique 5m/15m, rotation et changement de génération qui passe l’audit,
  puis échoue après corruption contrôlée d’un timestamp de côté.

Les changements D5/D4 déjà présents au démarrage ont été conservés. Aucun commit
n’a été créé : l’implémentation D5 préexistante était elle-même non suivie par Git,
avec d’autres modifications locales dans les collecteurs et les modules paper.

## Validation effectuée

- Backend : **40 tests réussis**, dont les 9 nouveaux tests D5.
- Régressions D4 : **12 tests réussis**, sur données synthétiques uniquement.
- Tests D5 ajoutés sous `python -B -O` : **9 tests réussis**.
- Les défauts de timestamp source à l’expiration et de rendement BTC ont été
  reproduits par échec des tests avant correction.
- Audit de `data/d5_live.db` par connexion SQLite `mode=ro`, dernier identifiant
  de session `aa38ec01-4615-411b-9ccd-087c4071392c` : 173 événements, 160 ticks
  BTC, **0 BOOK**, 0 marché couvert. `--require-smoke` retourne correctement 2.
  `SMOKE_VALIDATED=false`, `RESEARCH_ALLOWED=false`.

Preuves de cette reprise :

- `instrumentation_backend_tests.log`
- `instrumentation_optimized_tests.log`
- `instrumentation_resume_audit.json`

## Blocage réseau observé

Un appel actuel à la découverte publique avec `verify_tls=True` échoue avec
`CERTIFICATE_VERIFY_FAILED: Hostname mismatch` pour `gamma-api.polymarket.com`.
La commande locale `Resolve-DnsName gamma-api.polymarket.com -Type A` retourne :

```text
gamma-api.polymarket.com CNAME offre-illegale.anj.fr
offre-illegale.anj.fr    A     145.239.225.117
```

Aucune entrée Polymarket n’a été trouvée dans le fichier hosts local. Cette
observation explique le certificat incompatible reçu par la découverte. Aucun
changement DNS, contournement, ni désactivation TLS n’a été effectué.

La suite nécessite un accès autorisé et fonctionnel au service public : collecte
SHADOW bornée dans une nouvelle base, couverture des deux durées, rotation 5m et
reconnexion observées, puis audit. Une revue séparée après au moins 24 h reste
nécessaire avant toute recherche. Le succès synthétique ne valide pas le réseau.

Aucun ordre réel, passage en LIVE, usage de clé privée ou transfert de fonds.
Aucune ancienne base supprimée ou migrée.
