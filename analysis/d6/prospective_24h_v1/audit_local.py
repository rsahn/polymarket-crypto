"""Read-only inventory; no economic evaluation. Immutable SQLite ignores WAL explicitly."""
from pathlib import Path
import sqlite3,json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[3]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def utc(t):return datetime.datetime.fromtimestamp(t/1000,datetime.timezone.utc).isoformat() if t else None
def scan(c,table):
 n=0;start=end=previous=None;gaps=[];regress=0;nulls=0;src_min=src_max=None;segment=None;longest=(0,None,None);digest=hashlib.sha256()
 for row in c.execute(f'SELECT id,event_ts_ms,recv_ts_ms FROM {table} ORDER BY id'):
  ident,source,recv=row;n+=1;digest.update((json.dumps(row,separators=(',',':'))+'\n').encode())
  if source is None:nulls+=1
  else:src_min=source if src_min is None else min(src_min,source);src_max=source if src_max is None else max(src_max,source)
  if start is None:start=recv;segment=recv
  if previous is not None:
   delta=recv-previous
   if delta<0:regress+=1
   if delta>5000 or delta<0:
    if delta>5000:gaps.append({'before_ms':previous,'after_ms':recv,'gap_ms':delta})
    longest=max(longest,(previous-segment,segment,previous));segment=recv
  previous=end=recv
 if n:longest=max(longest,(end-segment,segment,end))
 return dict(event_count=n,start_ms=start,end_ms=end,start_utc=utc(start),end_utc=utc(end),span_hours=(end-start)/3600000 if n else 0,source_min_ms=src_min,source_max_ms=src_max,source_nulls=nulls,receive_regressions=regress,gap_threshold_ms=5000,gaps=gaps,max_gap_ms=max([x['gap_ms'] for x in gaps],default=0),longest_segment_at_5s_gap_threshold={'duration_hours':longest[0]/3600000,'start_ms':longest[1],'end_ms':longest[2]},timestamp_resolution='integer milliseconds; not a completeness guarantee',clock_rows_sha256=digest.hexdigest())
def main():
 p=ROOT/'data/poly_quant.db';before=(p.stat().st_size,p.stat().st_mtime_ns);h=sha(p)
 c=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True)
 result={'source':p.relative_to(ROOT).as_posix(),'file_sha256':h,'wal_present':Path(str(p)+'-wal').exists(),'schemas':dict(c.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('btc_ticks','poly_quotes')")),'btc_sources':c.execute('SELECT DISTINCT source,symbol FROM btc_ticks').fetchall(),'btc':scan(c,'btc_ticks'),'poly':scan(c,'poly_quotes')}
 c.close();result['source_unchanged']=before==(p.stat().st_size,p.stat().st_mtime_ns) and sha(p)==h
 inventory=[]
 paths=list((ROOT/'data').rglob('*.db'))
 for db in paths:
  if 'prospective_' in str(db):continue
  r={'source':db.relative_to(ROOT).as_posix(),'bytes':db.stat().st_size,'wal_bytes':Path(str(db)+'-wal').stat().st_size if Path(str(db)+'-wal').exists() else 0}
  if r['wal_bytes']:r['limitation']='immutable main-file view excludes WAL; not qualified as complete'
  try:
   con=sqlite3.connect(db.as_uri()+'?mode=ro&immutable=1',uri=True)
   tables={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")};r['tables']=sorted(tables)
   if 'events' in tables:
    r['first_event']=con.execute('SELECT event_id,kind,received_ts_ms FROM events ORDER BY event_id LIMIT 1').fetchone()
    r['last_event']=con.execute('SELECT event_id,kind,received_ts_ms FROM events ORDER BY event_id DESC LIMIT 1').fetchone()
   con.close()
  except sqlite3.Error as e:r['error']=str(e)
  inventory.append(r)
 result['inventory']=inventory
 out=ROOT/'analysis/d6/prospective_24h_v1/evidence/LOCAL_DATA_AUDIT.json'
 with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:result[k] for k in ('source','file_sha256','source_unchanged')}))
 for kind in ('btc','poly'):print(kind,json.dumps({k:v for k,v in result[kind].items() if k!='gaps'}))
if __name__=='__main__':main()
