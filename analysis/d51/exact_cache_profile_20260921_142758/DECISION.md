# Cache exact de profondeur — intégré après preuve technique

Clé binaire struct.pack des flottants : distinction +0/-0, aucun arrondi. Hors listes de <=20 paires de flottants natifs, retour à l'encodeur standard. Cache1024entrées LRU, indépendant par Store et actif seulement au schéma compressé2. Chaque événement, payload et côté est toujours inséré. Aucun format ni timestamp changé.

Sur77477messages :178735hits/131009misses (57.7%hits),44.159s et1754.49messages/s contre46.728s et1658.04 pour la référence indexée. La normalisation varie aussi ; ne pas attribuer toute la différence au cache.

Mesures alternées de40000profondeurs,3passagesparimplémentation : médiane référence0.764327s,cache0.677880s, environ11.3% de réduction du coût de pack. Un passage est presque identique ; gain limité, aucune promesse production.

Comparaison exhaustive des DB techniques PASS :77479événements,154872côtés,236ancres,2marchés. Toutes colonnes identiques sauf session_id et closed_at_ms technique propre à l'exécution. Payloads/profondeurs/timestamps byte-identiques. Tests synthétiques de types,mutation,borne,nonfinis PASS. Intégration dans Store.pack du schéma2 ; suite complète EXACT_DEPTH_CACHE_20260921 (consulter son résultat avant lancement).

Le précédent cache pickle reste abandonné. Ce candidat distinct utilise une clé binaire bornée et ses propres preuves. Aucune collecte source ni verdict historique modifié. Aucun D6/PAPER. Une nouvelle expérience prospective avec compteurs mur/CPU reste nécessaire avant la collecte longue.
