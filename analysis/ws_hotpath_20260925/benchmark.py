import cProfile,pstats,time,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from app.live.readonly_book_stream import StreamBook
s=StreamBook('m','c',('a','b'),10000,clock=lambda:1000)
s.connected_generation()
for t in ('a','b'):
 s.ingest({'event_type':'book','market':'c','asset_id':t,'timestamp':'1000','bids':[{'price':str(i/1000),'size':'1'} for i in range(1,100)],'asks':[{'price':str(i/1000),'size':'1'} for i in range(900,999)]})
e={'event_type':'price_change','market':'c','timestamp':'1000','price_changes':[{'asset_id':'a','side':'BUY','price':'.05','size':'2'}]}
p=cProfile.Profile();start=time.perf_counter();p.enable()
for _ in range(2000):s.ingest(e)
p.disable();elapsed=time.perf_counter()-start
print(json.dumps({'events':2000,'profiled_wall_seconds':elapsed,'available':s.read()['available'],'synthetic_offline_only':True}))
pstats.Stats(p).strip_dirs().sort_stats('cumtime').print_stats(12)
