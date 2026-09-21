import dataclasses,hashlib,importlib.util,json,pathlib,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from app.d5.identity import MarketIdentity
ref=ROOT/'analysis/d51/prepared_smoke3_20260921/frozen_code_and_protocol/backend/app/collectors/polymarket_ws.py'
spec=importlib.util.spec_from_file_location('reference_collector',ref);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
source=ROOT/'analysis/d51/raw_probe_20260921_125200';counts={};began=time.monotonic();hashes={}
for feed in ('5m','15m'):
 m=json.loads((source/(feed+'_identity.json')).read_text())['market'];i=MarketIdentity.from_market(m);assert i.fields()==dataclasses.asdict(i);assert list(i.fields())==[f.name for f in dataclasses.fields(i)]
 pair=[cls(feed,{'UP':i.token_up,'DOWN':i.token_down},None,i.expiry_ts_ms,identity=i,timestamp_contract='D5.1') for cls in (mod.PolymarketOrderbookCollector,PolymarketOrderbookCollector)]
 for c in pair:c._connection_generation=1
 n=0;digest=hashlib.sha256()
 with (source/(feed+'_raw.jsonl')).open(encoding='utf-8') as f:
  for line in f:
   row=json.loads(line)
   try:raw=json.loads(row['raw'])
   except (ValueError,TypeError):continue
   if not isinstance(raw,(dict,list)):continue
   a,b=[c.normalize_snapshot(raw,row['received_ms']) for c in pair]
   assert a==b,(feed,n);digest.update(json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False).encode());n+=1
 counts[feed]=n;hashes[feed]=digest.hexdigest()
r=dict(pass_all=True,counts=counts,snapshot_sha256=hashes,seconds=time.monotonic()-began,reference_sha256=hashlib.sha256(ref.read_bytes()).hexdigest(),candidate_sha256=hashlib.sha256((ROOT/'backend/app/collectors/polymarket_ws.py').read_bytes()).hexdigest(),scope='every normalized snapshot from the two bounded raw captures; identity fields equal dataclass reference')
with (source/'normalization_equivalence_duplicate_index.json').open('x',encoding='utf-8') as f:json.dump(r,f,indent=2)
print(json.dumps(r))
