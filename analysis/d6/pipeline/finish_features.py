"""Finish features in bounded event-id blocks, using existing Parquet only."""
import pathlib,sys,json,time,os,shutil,ast,datetime
from convert import atomic,memory_bytes,sha
import duckdb,pyarrow.parquet as pq

def finish(previous,out,block=100000):
 start=time.monotonic();out.mkdir(exist_ok=False);parquet=out/'parquet';parquet.mkdir();shards=out/'feature_shards';shards.mkdir()
 report=json.loads((previous/'raw_manifest.json').read_text());source=pathlib.Path(report['source'])
 if not report.get('source_unchanged') or not report.get('source_sha256'):raise RuntimeError('VERIFIED_SOURCE_MANIFEST_REQUIRED')
 if (source.stat().st_size,source.stat().st_mtime_ns)!=(report['source_bytes'],report['source_mtime_ns']):raise RuntimeError('SOURCE_METADATA_CHANGED')
 status={'pid':os.getpid(),'status':'RUNNING','stage':'FEATURES_BLOCKED_JOIN','source_read':'NONE, Parquet only','max_memory_bytes':0}
 def update(**extra):
  status.update(extra);status['elapsed_seconds']=time.monotonic()-start;status['memory_bytes']=memory_bytes();status['max_memory_bytes']=max(status['max_memory_bytes'],status['memory_bytes'] or 0);status['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();status['free_bytes']=shutil.disk_usage(out).free
  if status['free_bytes']<5*1024**3:raise RuntimeError('DISK_RESERVE')
  atomic(out/'progress.json',status)
 try:
  update(percent=0)
  for name in ('schema_info','sessions','markets','events','book_sides','anchors','hedge_attempts','btc'):
   shutil.copyfile(previous/'parquet'/f'{name}.parquet',parquet/f'{name}.parquet')
  atomic(out/'raw_manifest.json',report)
  c=duckdb.connect(str(out/'d6.duckdb'));c.execute("SET memory_limit='384MB'");c.execute('SET threads=1');c.execute('SET preserve_insertion_order=false');c.execute("SET temp_directory='"+str(out/'duckdb_tmp').replace("'","''")+"'")
  for p in parquet.glob('*.parquet'):c.execute("CREATE VIEW "+p.stem+" AS SELECT * FROM read_parquet('"+str(p).replace("'","''")+"')")
  tree=ast.parse((pathlib.Path(__file__).parent/'convert.py').read_text());query=next(n.value.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='query' for t in n.targets) and isinstance(n.value,ast.Constant))
  maximum=c.execute('SELECT max(event_id) FROM events').fetchone()[0];rows=0;qstart=time.monotonic()
  for lo in range(1,maximum+1,block):
   hi=min(maximum,lo+block-1);bounded=query.replace('FROM events e',f'FROM (SELECT * FROM events WHERE event_id BETWEEN {lo} AND {hi}) e')
   for side in ('u','d'):bounded=bounded.replace('JOIN book_sides '+side,f'JOIN (SELECT * FROM book_sides WHERE event_id BETWEEN {lo} AND {hi}) '+side)
   p=shards/f'{lo:09d}.parquet';c.execute("COPY ("+bounded+") TO '"+str(p).replace("'","''")+"' (FORMAT PARQUET,COMPRESSION ZSTD)");rows+=pq.ParquetFile(p).metadata.num_rows
   update(rows=rows,total=None,event_id_through=hi,event_id_max=maximum,percent=100*hi/maximum)
  update(stage='FEATURES_CONSOLIDATION',percent=None)
  dest=parquet/'book_features.parquet';c.execute("COPY (SELECT * FROM read_parquet('"+str(shards/'*.parquet').replace("'","''")+"')) TO '"+str(dest).replace("'","''")+"' (FORMAT PARQUET,COMPRESSION ZSTD)")
  c.execute("CREATE VIEW book_features AS SELECT * FROM read_parquet('"+str(dest).replace("'","''")+"')")
  report['essential_checks']={'source_book_rows':c.execute("SELECT count(*) FROM events WHERE kind='BOOK'").fetchone()[0],'feature_rows':c.execute('SELECT count(*) FROM book_features').fetchone()[0],'markets_by_duration':c.execute('SELECT market_duration,count(DISTINCT market_slug) FROM book_features GROUP BY 1').fetchall(),'post_expiry_envelopes':c.execute('SELECT count(*) FROM book_features WHERE greatest(event_ts_ms,received_ts_ms,available_ts_ms)>=expiry_ts_ms').fetchone()[0]}
  if report['essential_checks']['source_book_rows']!=report['essential_checks']['feature_rows']:raise RuntimeError('FEATURE_COUNT_MISMATCH')
  report.update(book_features_seconds=time.monotonic()-qstart,conversion_status='COMPLETE',quality_verdict='PENDING_FULL_REVIEW',parquet_bytes=sum(p.stat().st_size for p in parquet.glob('*.parquet')),feature_recovery_seconds=time.monotonic()-start,max_memory_bytes=status['max_memory_bytes'],recovery_from=str(previous),source_reopened_for_recovery=False)
  original=json.loads((out.parent/'data/progress.json').read_text());original_start=datetime.datetime.fromisoformat(original['updated_utc']).timestamp()-original['elapsed_seconds'];report['total_wall_seconds_including_failures_and_recovery']=time.time()-original_start
  report['source_unchanged']=(source.stat().st_size,source.stat().st_mtime_ns)==(report['source_bytes'],report['source_mtime_ns'])
  if not report['source_unchanged']:raise RuntimeError('SOURCE_METADATA_CHANGED')
  c.close();atomic(out/'conversion_report.json',report);update(status='COMPLETE',stage='COMPLETE',percent=100)
 except BaseException as exc:update(status='FAILED',error=repr(exc));raise
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--previous',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();finish(a.previous.resolve(),a.out.resolve())
