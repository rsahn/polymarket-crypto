import cProfile,datetime,io,json,pathlib,pstats,sys,tempfile,time,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from app.d5.store import Store,decode,encode
from app.d5.observer import Observer
from app.d5.features import BTCFeatures
from test_d5 import identity,snapshot
mode=sys.argv[1];assert mode in ('eager','lazy')
out=pathlib.Path(__file__).parent
features=BTCFeatures()
for n in range(1800):
 t=2+n*33;features.update(t,dict(price=50000+n%31,recv_ts_ms=t,event_ts_ms=t))
profile=cProfile.Profile();calls=0
with tempfile.TemporaryDirectory() as tmp:
 store=Store(pathlib.Path(tmp)/'synthetic.db',compress_payloads=True);observer=Observer(store);m=identity();observer.activate(m,1,0)
 def feature_at(t):
  global calls
  calls+=1;return features.at(t)
 start=time.perf_counter();profile.enable()
 for i in range(2000):
  t=60000+i;s=snapshot(m,t)
  for side in ('up','down'):
   s[side]['bids']=[[.4-j*.005,10.+j] for j in range(20)];s[side]['asks']=[[.6+j*.005,10.+j] for j in range(20)]
  observer.observe(m,1,s,(lambda t=t:feature_at(t)) if mode=='lazy' else feature_at(t),t)
 store.flush();profile.disable();elapsed=time.perf_counter()-start
 anchors=[decode(r[0]) for r in store.db.execute('SELECT features_json FROM anchors ORDER BY anchor_id')]
 digest=hashlib.sha256(encode(anchors).encode()).hexdigest();events=store.db.execute("SELECT count(*) FROM events WHERE kind='BOOK'").fetchone()[0];store.close()
buf=io.StringIO();pstats.Stats(profile,stream=buf).sort_stats('cumulative').print_stats(22)
with (out/(mode+'_profile.txt')).open('x',encoding='utf-8') as f:f.write(buf.getvalue())
r=dict(mode=mode,synthetic=True,book_events=events,btc_ticks_retained=1800,feature_calls=calls,seconds=elapsed,events_per_second=events/elapsed,anchor_count=len(anchors),anchor_features_sha256=digest,captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
with (out/(mode+'_result.json')).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2)
print(json.dumps(r));print(buf.getvalue())
