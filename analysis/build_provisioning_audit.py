"""Generate a code-linked requirements inventory, not an authority attestation."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.d6.real_execution_calibration_v1.preflight import REQUIRED
from analysis.d6.real_execution_calibration_v1.qualification import FIELDS

base = 'analysis/d6/real_execution_calibration_v1/'
blame = json.loads((ROOT/'analysis/provisioning_requirement_blame.json').read_text())
data = [
 ('Identité du wallet et du signataire', 'SDK réel + configuration publique + liaison propriétaire on-chain', 'identity', 'A/B pour adresses/signatures ; D pour attestation D6', 'Confusion EOA/proxy/deposit, mauvais maker', 'Lire les propriétés du vrai client et contrôler le propriétaire on-chain ; pas besoin de tiers commercial.'),
 ('Budget réellement disponible', 'CLOB balance + balanceOf RPC + réservations', 'account', 'A pour balances ; D pour réserve100 et preuve', 'Surengagement et cash indisponible', 'Collecteur GET/RPC distinct, même frontier et rapprochement ; une signature locale seule ne suffit pas.'),
 ('Marché et deux outcomes exacts', 'Gamma/CLOB + contrats condition/token', 'market', 'A pour mapping ; D pour enveloppe', 'Trader le mauvais token ou marché expiré', 'Comparer metadata et vrai abonnement WS ; signer uniquement le résultat observé.'),
 ('Chemin SDK signé testé', 'artefact SDK0.11.0 + tests crypto et source manifest', 'software', 'B pour intégrité/signature ; D pour version et preuve fraîche', 'Codec erroné, retries/allowance implicites', 'Attestation durable liée au hash du binaire ; vérifier le hash courant à chaque démarrage plutôt que réémettre le test toutes les5s.'),
 ('Inventaire et fees cohérents', 'collecteur direct CLOB/Data/RPC et archive', 'account', 'D', 'Exposition inconnue/observation partielle', 'Même invariant via collecteur séparé avec couverture vérifiable, sans société tierce obligatoire.'),
 ('Borne de fees entrée/sortie', 'paramètres marché + règles de règlement/arrondi', 'risk', 'A pour frais réels ; D pour borne round-trip/epoch', 'Dépasser budget via fees ou late fills', 'Calcul déterministe contrôlé indépendamment depuis règles réelles ; ne pas substituer fee_rate à fee_effect.'),
 ('Handoff accepté durablement', 'service/propriétaire indépendant + reçu du probe', 'custody', 'D ; B pour signature de reçu demandée dans cette mission', 'Exposition abandonnée après arrêt', 'Un service hors arbre supervisor, journal fsync, clé propre et reçu exact ; pas de flotte de tiers.'),
 ('Ledger vérifié et espace suffisant', 'Journal.read et disque D réel', 'runtime', 'D', 'Perte de journal ou disque plein', 'Rejouer chaîne localement + copie/checkpoint indépendante ; dimensionnement mesuré. Lettre D est choix de déploiement, pas invariant.'),
 ('Kill sans nouvelle entrée', 'test logiciel + probe du vrai canal custody', 'software', 'D', 'Ordre après kill, position abandonnée', 'Artefact de test lié au code + probe du déploiement, sans nouvel ordre réel.'),
 ('Réconciliation indépendante', 'CLOB/Data/RPC + tests d’inconnus', 'software', 'D', 'Double compte, fills manqués, confiance au POST', 'Observation séparée du submitter et contrôle de conservation ; aucun signataire commercial nécessaire.'),
 ('Erreur horloge bornée', 'source de temps indépendante et mesure RTT/dispersion', 'runtime', 'D pour100ms ; protocole NTP documenté, pas règle Polymarket', 'Accepter une preuve périmée/future', 'Mesure continue, borne et expiration locales monotoniques ; NTS/authentification si attaque réseau dans le modèle.'),
 ('Vrai book frais synchronisé', 'StreamBook réel de la session et son flux WS', 'runtime', 'A pour protocole ; D pour fraîcheur1000ms/enveloppe', 'Acheter sur book périmé/incomplet', 'Valider localement générations/tokens/âge du flux réel ; collecteur indépendant si isolation contre supervisor compromise requise.'),
 ('Tests du code déployé verts', 'rapports harness + manifest exact', 'software', 'D', 'Déployer un artefact non qualifié', 'Attestation liée au hash jusqu’à changement du binaire, pas exécution complète toutes les5s.'),
 ('Audit sans point critique ouvert', 'réviseur et audit de l’artefact/policy/déploiement', 'review', 'D ; aucune obligation réglementaire établie', 'Auto-déclaration READY malgré défauts de confiance', 'Une approbation humaine initiale versionnée + vérification mécanique du hash ; invalider sur changement.'),
]
checks = []
lines = ['AUDIT DE PROVENANCE ET PLAN 0→14',
         'Base inspectée : d6112e1. Blame = dernière introduction/modification de la ligne, pas preuve de son origine antérieure hors Git.',
         'A=API/SDK officiel ; B=nécessité cryptographique ; C=réglementation documentée ; D=choix sécurité D6 ; E=assumption/test promu par erreur.',
         'Les14 contrôles comme obligations de préflight sont D. Aucun C identifié dans le code ni les documents API consultés.',
         'Le mécanisme de preuve signée et les5s sont D ; authentifier une clé, le contenu et anti-rejeu relève de B si ce mécanisme est choisi.',
         'Le vrai bug E est détaillé dans PROVISIONING_ARCHITECTURE_REVIEW.txt. Aucun autre E n’est certifié accidentel sans historique probant.', '']
qrows = blame[base+'qualification.py']
for i, (name, meta) in enumerate(zip(REQUIRED, data), 1):
    matches = [r for r in qrows if "'"+name+"':" in r['source']]
    entry = dict(id=f'PROOF_{i:02}', check=name, objective=meta[0], producer=meta[2],
                 real_source=meta[1], origin=meta[3], risk=meta[4], simpler_equivalent_candidate=meta[5],
                 enforced_at=[dict(file=base+'qualification.py', **r) for r in matches],
                 required_data=list(FIELDS[name]),
                 signature='EIP191 D6_PROVENANCE_V1 + core.encoded(envelope without provenance_signature)',
                 public_key='Policy keys[key_id].address. NONE approved/provisioned; trading signer is not implicitly an authority.',
                 freshness='Current code: observed<=now<=valid_until; age<=5000ms, lifetime<=5000ms. WS receive additionally<=1000ms.',
                 verification='EvidenceVerifier.validate + ProductionAuthority.verify + preflight.evaluate; runtime bindings remain required.',
                 command='python analysis/production_provisioning_check.py --inbox <inbox> --policy <trust-policy.json> --approved-policy-digest <external-approved-digest> --output <new-report.json>',
                 pass_predicate=[r['source'].strip() for r in matches if 'lambda:' in r['source']],
                 automation='Automatic acquisition/validation; principal and policy approval human. 07 owner acceptance human/service-authorized;14 independent review human.')
    checks.append(entry)
    lines += [f"{entry['id']} {name}",f"Objectif : {meta[0]}",f"Origine : {meta[3]}",
              f"Producteur / source : {meta[2]} / {meta[1]}",
              'Données : '+', '.join(FIELDS[name]),
              'Imposé par : '+' ; '.join(f"{base}qualification.py:{r['line']} [{r['commit'][:12]}]" for r in matches),
              'PASS exact : '+' '.join(entry['pass_predicate']),
              f'Risque : {meta[4]}',f'Alternative à démontrer : {meta[5]}',
              'Signature/clé/freshness/vérification/commande/automatisation : contrat commun ci-dessous.', '']
lines += ['CONTRAT COMMUN À CHAQUE PROOF_01…14',
          checks[0]['signature'], checks[0]['public_key'], checks[0]['freshness'],
          checks[0]['verification'], checks[0]['command'], checks[0]['automation'],
          'Configuration payload et compléments runtime exacts : PRODUCTION_PROVISIONING.txt, sections01…14.',
          'La commande vérifie des fichiers fournis ; elle ne produit ni signe la preuve et ne donne jamais une autorisation LIVE.', '',
          'INVENTAIRE EXHAUSTIF DES LIGNES DE GARDE Provider / Authority / Custody / assembly',
          'Classification : D sauf primitives cryptographiques B indiquées ; les commentaires de code ne constituent pas une obligation officielle.', '']
guards=[]
for filename in ('production_authority.py','production_evidence_source.py','production_provider.py',
                 'custody.py','manual_custody.py','launch.py','runner.py','adapters.py','capacity.py','engine.py'):
    for r in blame[base+filename]:
        src=r['source'].strip()
        if any(s in src for s in ('raise ', 'return False', '!=', ' is True',' is not True','<=5000','MAX_BYTES=', 'REQUIRED_FREE_BYTES=', 'KEY')):
            category='D (primitive B sous-jacente)' if any(s in src.lower() for s in ('signature','recover_message','digest','nonce','key_id')) else 'D'
            guards.append(dict(file=base+filename,classification=category,**r))
            lines.append(f"{base}{filename}:{r['line']} [{r['commit'][:12]}] {category} | {src}")
(ROOT/'analysis/provisioning_proof_plan.json').write_text(json.dumps({'proofs':checks,'guard_inventory':guards},indent=2,ensure_ascii=False),encoding='utf-8')
(ROOT/'analysis/PROVISIONING_REQUIREMENTS_AUDIT.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'proofs':len(checks),'guard_lines':len(guards)}))
