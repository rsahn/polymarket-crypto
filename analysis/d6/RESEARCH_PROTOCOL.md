# D6 — protocole préparé, aucune recherche exécutée

Statut PREPARATION_ONLY. Aucun accès à la base active, modification du collecteur/superviseur, ordre, wallet ou changement de mode/RESEARCH_ALLOWED. Les contrats exécutables dans tests/ utilisent uniquement des fixtures en mémoire.

## Objectifs et familles séparées

Question explicative : quelles informations antérieures expliquent le côté, le timing et la quantité des achats publics ? Prédiction et association ne prouvent pas la causalité ni l'information privée du trader. Si le timestamp API correspond à un règlement, l'heure de décision reste inconnue.

| Famille | Objectif futur | Critère de comparaison |
|---|---|---|
| BONEREAPER_LIKE | Reproduire les propriétés comportementales observables | Alternance, bilatéralité, inventaire, timing, tailles, coûts de paire et exposition directionnelle |
| D6_OPTIMIZED | Chercher ultérieurement une politique indépendante | Objectif net et contraintes de risque/exécution préenregistrés ; aucune obligation d'imitation |

Aucune optimisation aujourd'hui. Registres séparés par family, experiment_id, versions code/data/features/exécution, split hash et seed. Compter tous les essais, y compris perdants ; ne pas changer de famille pour masquer un résultat.

Référence descriptive : ../bonereaper_public/REPORT.md. Proxy actuel vérifié : 0xeebde7a0e019a63e6b476eb425505b7b3e6eba30. Ne pas assimiler l'ancienne adresse au proxy. Les achats bilatéraux fréquents n'impliquent ni arbitrage systématique sous 1, ni neutralisation obligatoire, ni résidu accidentel. La semaine historique ne recouvre pas D5.

## Pipeline futur, bloqué jusqu'à validation

1. Confirmer fin propre et fermeture du writer D5. Examiner rapport qualité, integrity_check, identités, expirations, gaps et deux replays NoTrade. Des empreintes identiques ne suffisent pas à elles seules.
2. Obtenir acceptation explicite de la revue et autorisation de recherche. Ne pas basculer automatiquement RESEARCH_ALLOWED.
3. Geler manifeste du fichier fermé/copie validée : hash, taille, session, schéma, code, début/fin réels, décisions qualité. Futur adaptateur strictement read-only, refus de base active ou manifeste incomplet. Aucun chargeur réel implémenté ici.
4. Nouvelle extraction Bonereaper couvrant EXACTEMENT [début réel D5, fin réelle D5). Conserver réponses brutes, provenance, identité, doublons ambigus. Les bins seconde chevauchant les bornes milliseconde vont dans une partition ambiguë, sans timestamps inventés. Historique de bootstrap d'inventaire séparé de la cohorte.
5. Contrôler identifiabilité temporelle puis jointure JOIN_SPEC. Publier non-matchs et exclusions avant résultats.
6. Geler partitions chronologiques par marché. TRAIN : transformations et découverte ; VALIDATION : sélection ; OOS : une ouverture après gel intégral.
7. Tester H1–H8 et modèles nuls ; seulement ensuite expérimenter les politiques autorisées. Registre complet des essais et analyses de sensibilité.
8. Publier résultats positifs, nuls et négatifs ; toute retouche après OOS requiert un nouvel OOS indépendant.

## Unités et mesures

Côté : UP/DOWN conditionnel à BUY ; groupes mixtes dans la même seconde ambigus. Timing : grille causale 1 s par marché valide avec achat ET non-achat ; sans dénominateur d'opportunités, aucune explication du timing. Taille : quantité API, pas taille d'ordre initial ; jamais utiliser le fill courant dans ses propres features.

BONEREAPER_LIKE : distributions fills/marché, bilatéralité, transitions, délais, tailles, coûts, imbalance et résidus par âge ; calibration side/timing et erreur taille. Préenregistrer distances (ex. Wasserstein), poids et normalisations TRAIN avant sélection. Les mêmes censures s'appliquent aux références.

D6_OPTIMIZED : objectif de rendement net ajusté au risque et contraintes dures à figer avant optimisation, sans cible de profit imposée. Capital 500 global, pas par marché. Métriques détaillées dans EXECUTION_MODEL.

Tenir compte des dépendances par marché et blocs temporels, surtout 5m/15m simultanés. Une journée ne démontre pas une stabilité inter-régimes. Publier les effectifs utiles et UNKNOWN plutôt que réduire discrètement les exigences.

## Ce qui peut manquer après D5

Activité Bonereaper contemporaine complète ; inventaire initial/transferts ; temps de décision/exécution et ordre intraseconde ; maker/taker et annulations ; frais/rebates historiques ; queue et renouvellement de liquidité ; oracle/règlement/token burns ; profondeur non capturée et journées supplémentaires. Les données manquantes peuvent rendre une hypothèse non testable.
