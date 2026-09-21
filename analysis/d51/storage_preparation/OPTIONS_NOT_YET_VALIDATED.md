# Stockage prospectif — options non validées

21 septembre 2026. Documentation technique uniquement pendant la revue du deuxième smoke. Aucun benchmark lourd, scan supplémentaire, compression ou modification de DB réalisé.

Volume C: NTFS, allocation 4096 octets, environ 105 Gio libres au relevé 11:13 Paris. Les projections de capacité doivent employer les octets réellement alloués, pas seulement la taille logique.

## Option transparente à évaluer, pas encore adoptée

Microsoft documente une compression NTFS sans perte, transparente aux applications. Le marquage d'un nouveau répertoire vide peut s'appliquer aux futurs fichiers. Cela permettrait en principe de conserver SQLite et sa chaîne d'audit existante, mais le gain et la latence doivent être mesurés. Aucune promesse de facteur de réduction : les BLOB zlib actuels peuvent mal se recompresser.

Limiter un éventuel essai à un NOUVEAU dossier de fixtures, jamais aux bases existantes, à une racine, au volume entier ou au système. Ne pas utiliser /EXE (fichiers peu modifiés), /CompactOs, une récursion globale ou la compression d'une DB source. Aucun essai lancé ici.

Microsoft avertit qu'une compression de fichier dépassant 30 Go peut échouer. Une collecte longue monolithique n'est donc pas réputée résolue par cette option. Un partitionnement demanderait preuve de continuité des générations/ancres/ordre et replay identique entre frontières ; il ne doit pas créer artificiellement des trous de feed.

## Option colonne/Parquet

Le convertisseur existant est une vue dérivée incomplète, pas une archive primaire. Une version réellement sans perte doit conserver toutes les colonnes, types SQLite (y compris BLOB/TEXT), payload BOOK, profondeurs, horloges, métadonnées, contrôles, événements BTC et état des ancres. Vérifier un flux canonique complet et les deux replays, pas uniquement les comptes de lignes. Garder les sources existantes. Une copie comprimée ajoutée à une source conservée augmente le pic de stockage.

## Condition de décision

D'abord verdict du smoke. Ensuite benchmark borné de fixtures et/ou nouveau dérivé autorisé de source fermée, sans modifier la source ; mesurer CPU/latence/écriture/lecture/allocation/intégrité/replays. Figer la durée et les partitions avant les résultats D6. Aucun changement opportuniste de seuil de qualité ou de significativité. Le minimum de 30 marchés OOS par durée appartient à l'ancien plan : l'éventuel nouveau plan doit préciser son effectif et ses limites avant résultats, conformément à USER_PROTOCOL.md, qui autorise de réserver une validation statistique supplémentaire au futur PAPER sans inventer une significativité.

## Sources primaires consultées

- https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/compact — portée de /c, héritage du répertoire, /EXE destiné aux fichiers rarement modifiés.
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-compression-and-decompression — transparence, conservation des données, réserve sur fichiers >30 Go.

Ces sources décrivent les mécanismes, pas leurs performances sur ce dataset. Aucune option n'est marquée validée ni appliquée.
