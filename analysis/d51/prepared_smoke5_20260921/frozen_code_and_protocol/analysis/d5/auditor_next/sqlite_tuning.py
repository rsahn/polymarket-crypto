"""Connection-local SQLite tuning: no schema, data, journal or checkpoint writes."""
import sqlite3
from urllib.parse import urlsplit,parse_qs
CACHE_KIB=131072

def connect_ro(database_uri,*,cache_kib=CACHE_KIB,factory=sqlite3.Connection,**kwargs):
 if not str(database_uri).startswith('file:') or parse_qs(urlsplit(str(database_uri)).query).get('mode')!=['ro']:
  raise ValueError('Explicit mode=ro required')
 if not 1<=cache_kib<=262144:raise ValueError('Cache outside bounded memory limit')
 c=sqlite3.connect(database_uri,uri=True,factory=factory,**{k:v for k,v in kwargs.items() if k!='uri'})
 try:
  sqlite3.Connection.execute(c,'PRAGMA query_only=ON')
  sqlite3.Connection.execute(c,f'PRAGMA cache_size=-{cache_kib}')
  return c
 except BaseException:
  c.close();raise
