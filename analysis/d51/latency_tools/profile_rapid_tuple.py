"""Technical hot-path profiling only; captured public frames, no strategy research."""
import cProfile,datetime,hashlib,io,json,pathlib,pstats,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from app.d5.identity import MarketIdentity
from app.d5.store import Store,code_version
sys.path.insert(0,str(ROOT/'analysis/d51/native_json_candidate'))
import rapid_tuple_encoder as encoder
import app.d5.store as store_module
store_module.encode=encoder.encode
from app.d5.observer import Observer
from app.collectors.stage_timing import StageTiming
source=ROOT/'analysis/d51/raw_probe_20260921_125200'
out=ROOT/'analysis/d51'/('rapid_tuple_profile_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir(exist_ok=False)
rows=[];collectors={};identities={};hashes={}
for feed in ('5m','15m'):
 p=source/(feed+'_raw.jsonl');hashes[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
 market=json.loads((source/(feed+'_identity.json')).read_text())['market'];i=MarketIdentity.from_market(market);identities[feed]=i
 c=PolymarketOrderbookCollector(feed,{'UP':i.token_up,'DOWN':i.token_down},None,i.expiry_ts_ms,identity=i,timestamp_contract='D5.1');c._connection_generation=1;collectors[feed]=c
 with p.open(encoding='utf-8') as f:
  for n,line in enumerate(f):
   r=json.loads(line);rows.append((r['monotonic_ns'],feed,r))
rows.sort(key=lambda x:x[0]);store=Store(out/'technical_only.db',{'technical_diagnostic_only':True},compress_payloads=True);obs=Observer(store)
for feed,i in identities.items():obs.activate(i,1,rows[0][2]['received_ms'])
stages=StageTiming()
profiling=False;profile=cProfile.Profile();timing=dict(parse=0.,normalize=0.,observer_and_store=0.);frames=0;lastflush=rows[0][2]['received_ms'];began=time.perf_counter()
if profiling:profile.enable()
for _,feed,r in rows:
 t=time.perf_counter();started=stages.start()
 try:payload=json.loads(r['raw'])
 except (ValueError,TypeError):continue
 timing['parse']+=time.perf_counter()-t;stages.finish(feed+':parse',started)
 if not isinstance(payload,(dict,list)):continue
 t=time.perf_counter();started=stages.start();snapshot=collectors[feed].normalize_snapshot(payload,r['received_ms']);timing['normalize']+=time.perf_counter()-t;stages.finish(feed+':normalize',started)
 t=time.perf_counter();started=stages.start();obs.observe(identities[feed],1,snapshot,{},r['received_ms']);timing['observer_and_store']+=time.perf_counter()-t;stages.finish(feed+':observer_and_store',started);frames+=1
 if r['received_ms']-lastflush>=500:
  started=stages.start();store.flush();stages.finish('commit',started);lastflush=r['received_ms']
store.flush();profile.disable();elapsed=time.perf_counter()-began;counts=dict(store.counts);store.close('TECHNICAL_DIAGNOSTIC_ONLY')
buf=io.StringIO();pstats.Stats(profile,stream=buf).sort_stats('cumulative').print_stats(45) if profiling else buf.write('Profiling disabled for throughput measurement.\n')
(out/'profile.txt').write_text(buf.getvalue(),encoding='utf-8')
result=dict(candidate_encoder_sha256=hashlib.sha256((ROOT/'analysis/d51/native_json_candidate/rapid_tuple_encoder.py').read_bytes()).hexdigest(),rapidjson_version=encoder.rapidjson.__version__,technical_only=True,not_D6=True,not_a_quality_smoke=True,profile_overhead_present=profiling,frames=frames,seconds=elapsed,frames_per_second=frames/elapsed,timing_seconds=timing,stage_counters=stages.snapshot(),capture_span_seconds=(rows[-1][0]-rows[0][0])/1e9,counts=counts,source_hashes=hashes,code_version=code_version())
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(str(out));print(json.dumps(result));print(buf.getvalue())
