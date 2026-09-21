"""D5 read-only export -> Parquet -> DuckDB. Never writes source SQLite."""
import sys,pathlib,sqlite3,json,time,os,hashlib,zlib,datetime,shutil,ctypes
HERE=pathlib.Path(__file__).resolve().parent;D6=HERE.parent;ROOT=D6.parents[1]
sys.path.insert(0,str(D6/'vendor'))
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds
import duckdb
TABLES=('schema_info','sessions','markets','events','book_sides','anchors','hedge_attempts')
def decode(v):
 if isinstance(v,bytes):
  try:v=zlib.decompress(v)
  except zlib.error:pass
 return json.loads(v)
def atomic(p,data):
 text=json.dumps(data,indent=2,ensure_ascii=False);t=p.with_suffix('.tmp');t.write_text(text,encoding='utf-8')
 for attempt in range(12):
  try:t.replace(p);return
  except PermissionError:time.sleep(min(.05*(attempt+1),.3))
 if p.name=='progress.json':
  # A monitoring reader can deny rename on Windows. Status is advisory, never abort data work.
  try:p.write_text(text,encoding='utf-8')
  except OSError:pass
 else:t.replace(p)
def sha(path,progress=None):
 h=hashlib.sha256();done=0
 with path.open('rb') as f:
  while b:=f.read(8*1024*1024):
   h.update(b);done+=len(b)
   if progress:progress(done)
 return h.hexdigest()
def memory_bytes():
 class Counters(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ('peak','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
 m=Counters();m.cb=ctypes.sizeof(m);fn=ctypes.windll.psapi.GetProcessMemoryInfo
 fn.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
 return int(m.working) if fn(ctypes.c_void_p(-1),ctypes.byref(m),m.cb) else None

def convert(source,out,batch_size=5000,resume_from=None):
 source=pathlib.Path(source).resolve();out=pathlib.Path(out).resolve()
 if out.exists():raise FileExistsError('New output directory required')
 out.mkdir(parents=True);parquet=out/'parquet';parquet.mkdir();start=time.monotonic();state={'pid':os.getpid(),'status':'RUNNING','source':str(source)}
 def update(**kwargs):
  state.update(kwargs);state['memory_bytes']=memory_bytes();state['max_memory_bytes']=max(state.get('max_memory_bytes',0),state['memory_bytes'] or 0);state.update(elapsed_seconds=time.monotonic()-start,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),free_bytes=shutil.disk_usage(out).free)
  if state['free_bytes']<5*1024**3:raise RuntimeError('DISK_RESERVE_5_GIB')
  atomic(out/'progress.json',state)
  print(json.dumps(state),flush=True)
 before=(source.stat().st_size,source.stat().st_mtime_ns)
 resume=pathlib.Path(resume_from).resolve() if resume_from else None
 if resume:
  previous=json.loads((resume/'raw_manifest.json').read_text(encoding='utf-8'))
  if previous['source']!=str(source) or (previous['source_bytes'],previous['source_mtime_ns'])!=before:raise RuntimeError('RESUME_SOURCE_FINGERPRINT_CHANGED')
 report={'source':str(source),'source_bytes':before[0],'source_mtime_ns':before[1],'tables':{},'source_unchanged':None,'historical_audit':'separate, not modified','dataset_label':'prospective D5 short-window dataset','is_24h_validation':False,'omissions':{'events.BOOK.payload_json':'Derived export only: redundant snapshot JSON omitted; envelope, identity, full book_sides depths/timestamps/source hashes retained. RAW SQLite untouched.'}}
 db=None
 try:
  db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
  db.row_factory=sqlite3.Row
  report['sessions']=[dict(r) for r in db.execute('SELECT * FROM sessions')]
  tail=db.execute("SELECT event_id,kind,payload_json FROM events ORDER BY event_id DESC LIMIT 20").fetchall()
  report['tail_markers']=[{'event_id':r[0],'kind':r[1],'payload':decode(r[2])} for r in tail if r[1] in ('COLLECTION_STOP','SESSION_END')]
  if not any(x['kind']=='SESSION_END' for x in report['tail_markers']):raise RuntimeError('CLOSED_DATASET_MARKER_REQUIRED')
  atomic(out/'raw_manifest.json',report)
  for step,table in enumerate(TABLES,1):
   begin=time.monotonic();update(stage=f'[{step}/10] {table}',rows=0,total=None,percent=None)
   cols=db.execute(f'PRAGMA table_info({table})').fetchall()
   fields=[];blobcols=[];names=[];select=[]
   for c in cols:
    name,typ=c[1],c[2].upper();names.append(name)
    if 'INT' in typ:t=pa.int64()
    elif any(v in typ for v in ('REAL','FLOAT','DOUBLE')):t=pa.float64()
    elif 'BLOB' in typ:t=pa.binary();blobcols.append(name)
    else:t=pa.string()
    fields.append(pa.field(name,t))
    select.append("CASE WHEN kind='BOOK' THEN NULL ELSE payload_json END AS payload_json" if table=='events' and name=='payload_json' else '"'+name+'"')
   fields.extend(pa.field(n+'_storage',pa.string()) for n in blobcols)
   schema=pa.schema(fields);total=db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
   done=0;path=parquet/f'{table}.parquet';old=resume/'parquet'/f'{table}.parquet' if resume else None
   if old and old.exists() and pq.ParquetFile(old).metadata.num_rows==total:
    shutil.copyfile(old,path);report['tables'][table]={'rows':total,'bytes':path.stat().st_size,'seconds':time.monotonic()-begin,'sha256':sha(path),'reused_from':str(old)};continue
   prefix=pq.ParquetFile(old) if old and old.exists() and table=='events' else None
   last_id=0
   if prefix:
    for batch in prefix.iter_batches(columns=['event_id']):
     if batch.num_rows:last_id=batch.column(0)[-1].as_py()
    done=prefix.metadata.num_rows
   cursor=db.execute(f'SELECT {",".join(select)} FROM {table}'+(' WHERE event_id>? ORDER BY event_id' if prefix else ''),(last_id,) if prefix else ())
   with pq.ParquetWriter(path,schema,compression='zstd',compression_level=3,use_dictionary=True) as writer:
    if prefix:
     for batch in prefix.iter_batches(batch_size=batch_size):writer.write_batch(batch)
    while batch:=cursor.fetchmany(batch_size):
     rows=[]
     for raw in batch:
      row=dict(raw)
      for n in blobcols:
       value=row[n];row[n+'_storage']='zlib' if isinstance(value,bytes) else 'text' if value is not None else None
       if isinstance(value,str):row[n]=value.encode('utf-8')
      rows.append(row)
     writer.write_table(pa.Table.from_pylist(rows,schema=schema));done+=len(rows)
     update(rows=done,total=total,percent=100*done/total if total else 100,rows_per_second=done/max(.001,time.monotonic()-begin))
   exported=pq.ParquetFile(path).metadata.num_rows
   if exported!=total:raise RuntimeError('EXPORT_COUNT_MISMATCH_'+table)
   report['tables'][table]={'rows':done,'bytes':path.stat().st_size,'seconds':time.monotonic()-begin,'sha256':sha(path)}
   atomic(out/'conversion_report.json',report)
  db.close();db=None
  update(stage='[8/10] RAW SHA-256',percent=0,rows=None,total=before[0])
  last=[0.]
  def hash_progress(done):
   if time.monotonic()-last[0]>2:last[0]=time.monotonic();update(bytes_hashed=done,percent=100*done/before[0])
  report['source_sha256']=sha(source,hash_progress)
  report['source_unchanged']=before==(source.stat().st_size,source.stat().st_mtime_ns)
  if not report['source_unchanged']:raise RuntimeError('SOURCE_CHANGED')
  atomic(out/'raw_manifest.json',report)
  update(stage='[9/10] BTC structural extraction',rows=0,total=None,percent=None)
  btc=[]
  scanner=ds.dataset(parquet/'events.parquet').scanner(filter=ds.field('kind')=='BTC',columns=['event_id','event_ts_ms','received_ts_ms','available_ts_ms','payload_json'])
  for batch in scanner.to_batches():
   for row in batch.to_pylist():
    payload=decode(row.pop('payload_json'));row['price']=float(payload['price']);btc.append(row)
  pq.write_table(pa.Table.from_pylist(btc,schema=pa.schema([pa.field(n,pa.int64()) for n in ('event_id','event_ts_ms','received_ts_ms','available_ts_ms')]+[pa.field('price',pa.float64())])),parquet/'btc.parquet',compression='zstd')
  update(stage='[10/10] DuckDB catalog and essential features',rows=None,total=None,percent=None)
  conn=duckdb.connect(str(out/'d6.duckdb'));conn.execute("SET memory_limit='384MB'");conn.execute('SET threads=2');conn.execute('SET preserve_insertion_order=false')
  conn.execute("SET temp_directory='"+str(out/'duckdb_tmp').replace("'","''")+"'")
  for p in parquet.glob('*.parquet'):
   conn.execute("CREATE VIEW "+p.stem+" AS SELECT * FROM read_parquet("+chr(39)+str(p).replace(chr(39),chr(39)*2)+chr(39)+")")
  query='''SELECT e.event_id,e.session_id,e.market_duration,e.market_slug,e.condition_id,e.token_up,e.token_down,e.generation,
 e.event_ts_ms,e.received_ts_ms,e.available_ts_ms,m.expiry_ts_ms,
 u.event_ts_ms up_source_ms,u.received_ts_ms up_received_ms,d.event_ts_ms down_source_ms,d.received_ts_ms down_received_ms,
 u.best_bid up_bid,u.best_ask up_ask,u.best_bid_qty up_bid_qty,u.best_ask_qty up_ask_qty,
 d.best_bid down_bid,d.best_ask down_ask,d.best_bid_qty down_bid_qty,d.best_ask_qty down_ask_qty,
 u.spread up_spread,d.spread down_spread,u.best_ask+d.best_ask pair_ask_cost,
 (u.best_bid_qty-u.best_ask_qty)/nullif(u.best_bid_qty+u.best_ask_qty,0) up_imbalance,
 (d.best_bid_qty-d.best_ask_qty)/nullif(d.best_bid_qty+d.best_ask_qty,0) down_imbalance,
 greatest(e.available_ts_ms,e.received_ts_ms,e.event_ts_ms,u.event_ts_ms,u.received_ts_ms,d.event_ts_ms,d.received_ts_ms) causal_bound_ms,
 (m.expiry_ts_ms-e.available_ts_ms)/1000.0 remaining_seconds,
 (e.available_ts_ms-(m.expiry_ts_ms-CASE WHEN e.market_duration='5m' THEN 300000 ELSE 900000 END))/1000.0 market_age_seconds
 FROM events e JOIN markets m USING(condition_id,market_slug)
 JOIN book_sides u ON u.event_id=e.event_id AND u.side='UP'
 JOIN book_sides d ON d.event_id=e.event_id AND d.side='DOWN'
 WHERE e.kind='BOOK' '''
  qstart=time.monotonic();dest=str(parquet/'book_features.parquet').replace("'","''")
  conn.execute("COPY ("+query+") TO '"+dest+"' (FORMAT PARQUET,COMPRESSION ZSTD)")
  report['book_features_seconds']=time.monotonic()-qstart
  conn.execute("CREATE VIEW book_features AS SELECT * FROM read_parquet('"+dest+"')")
  report['essential_checks']={'source_book_rows':conn.execute("SELECT count(*) FROM events WHERE kind='BOOK'").fetchone()[0],'feature_rows':conn.execute('SELECT count(*) FROM book_features').fetchone()[0],'markets_by_duration':conn.execute('SELECT market_duration,count(DISTINCT market_slug) FROM book_features GROUP BY 1').fetchall(),'post_expiry_envelopes':conn.execute('SELECT count(*) FROM book_features WHERE greatest(event_ts_ms,received_ts_ms,available_ts_ms)>=expiry_ts_ms').fetchone()[0]}
  report['max_memory_bytes']=state.get('max_memory_bytes');report['conversion_status']='COMPLETE';report['quality_verdict']='PENDING_FULL_REVIEW';report['elapsed_seconds']=time.monotonic()-start;report['parquet_bytes']=sum(p.stat().st_size for p in parquet.glob('*.parquet'));conn.close()
  atomic(out/'conversion_report.json',report);update(status='COMPLETE',percent=None)
 except BaseException as exc:
  state.update(status='FAILED',error=repr(exc));atomic(out/'progress.json',state);raise
 finally:
  if db:db.close()
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--resume-from',type=pathlib.Path);a=p.parse_args();convert(a.source,a.out,resume_from=a.resume_from)
