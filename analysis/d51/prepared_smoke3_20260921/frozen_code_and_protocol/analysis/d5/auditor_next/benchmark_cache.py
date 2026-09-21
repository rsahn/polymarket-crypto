import sys,pathlib,json,time,datetime,statistics
sys.path.insert(0,str(pathlib.Path('analysis/d5/auditor_next').resolve()))
from sqlite_tuning import connect_ro
source=pathlib.Path('data/d5_24h_20260920_085530/d5_live_24h_20260920_124822.db').resolve();before=(source.stat().st_size,source.stat().st_mtime_ns)
out=pathlib.Path('analysis/d5/cache_probe_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
sql="SELECT count(*),sum(b.token_id != CASE WHEN b.side='UP' THEN e.token_up ELSE e.token_down END) FROM book_sides b JOIN events e USING(event_id) WHERE b.event_id BETWEEN 1 AND 60000"
results=[]
for cache in (2000,131072,131072,2000):
 db=connect_ro(source.as_uri()+'?mode=ro',cache_kib=cache);start=time.monotonic();cpu=time.process_time();db.set_progress_handler(lambda:int(time.monotonic()-start>90),10000)
 try:
  result=list(db.execute(sql));entry={'cache_kib':cache,'seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,'result':result}
 except Exception as e:entry={'cache_kib':cache,'seconds':time.monotonic()-start,'error':repr(e)}
 finally:db.close()
 results.append(entry);print(json.dumps(entry),flush=True)
 report={'scope':'Bounded read-only probe over event_id 1..60000; not an audit result and not a full integrity runtime estimate','sql':sql,'results':results,'source_stat_unchanged':before==(source.stat().st_size,source.stat().st_mtime_ns)}
 (out/'BENCHMARK.json').write_text(json.dumps(report,indent=2))
report['equivalent']=all(r.get('result')==results[0].get('result') and 'error' not in r for r in results)
if report['equivalent']:
 med={c:statistics.median(r['seconds'] for r in results if r['cache_kib']==c) for c in (2000,131072)};report['median_seconds']=med;report['probe_speedup']=med[2000]/med[131072]
(out/'BENCHMARK.json').write_text(json.dumps(report,indent=2));print(json.dumps({'out':str(out),**report}),flush=True)
