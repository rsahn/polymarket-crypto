import sys,pathlib,sqlite3,json,time,statistics,hashlib,struct
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[2];sys.path.insert(0,str(ROOT/'backend'))
from codec import pack,unpack
from app.d5.store import Store,decode,encode
source=ROOT/'analysis/d51/full_stage_profile_20260921_154248/technical_only.db'
db=sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON')
values=[decode(r[0]) for r in db.execute("SELECT payload_json FROM events WHERE kind='BOOK' ORDER BY event_id LIMIT 5000")];db.close()
ref=Store.__new__(Store);ref.schema_version=2
samples={'json_zlib':[],'guarded_msgpack_zlib':[]};sizes={};hashes={}
for i in range(3):
    for name,fn in ((('json_zlib',ref._pack_uncached),('guarded_msgpack_zlib',pack)) if i%2==0 else (('guarded_msgpack_zlib',pack),('json_zlib',ref._pack_uncached))):
        begin=time.perf_counter();out=[fn(v) for v in values];samples[name].append(time.perf_counter()-begin)
        sizes[name]=sum(len(x.encode() if isinstance(x,str) else x) for x in out)
        if name=='guarded_msgpack_zlib':
            assert all(encode(unpack(x))==encode(v) for x,v in zip(out,values))
            hashes[name]=hashlib.sha256(b''.join(out)).hexdigest()
for v in (-0.0,0.0,1e-300,1e300):assert struct.pack('>d',unpack(pack(v)))==struct.pack('>d',v)
for v in (float('nan'),float('inf'),float('-inf'),1<<64):
    try:pack(v)
    except ValueError:pass
    else:raise AssertionError('Invalid accepted')
r=dict(technical_only=True,production_unchanged=True,n=len(values),samples_seconds=samples,median_seconds={k:statistics.median(v) for k,v in samples.items()},total_encoded_bytes=sizes,canonical_decoded_equality=True,float_bits_test='PASS',invalid_rejections='PASS',candidate_sha256=hashes)
with (P/'benchmark.json').open('x') as f:json.dump(r,f,indent=2)
print(json.dumps(r))
