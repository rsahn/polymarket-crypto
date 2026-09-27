"""Offline new-observation overhead and historical sample timeline; no economics."""
import json,zlib,hashlib,shutil,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))
from analysis.d6.causal_capture_24h_v1.collector import Journal,BookCapture,storage_preflight,source_seal
OUT=Path(__file__).parent/'evidence'

def main():
 rows=json.loads(zlib.decompress((OUT/'HISTORICAL_SAMPLE.json.zlib').read_bytes()))
 timelines={}
 for r in rows:
  key=r['market']+'|'+r['asset_id'];t=timelines.setdefault(key,{'market':r['market'],'token':r['asset_id'],'events':0,'book_anchors':0,'receive_ties':0,'receive_regressions':0,'first_receive':r['timestamp_received'],'last_receive':None,'event_types':{}})
  t['events']+=1;t['book_anchors']+=int(r['event_type']=='book');t['event_types'][r['event_type']]=t['event_types'].get(r['event_type'],0)+1
  if t['last_receive'] is not None:
   t['receive_ties']+=int(t['last_receive']==r['timestamp_received']);t['receive_regressions']+=int(t['last_receive']>r['timestamp_received'])
  t['last_receive']=r['timestamp_received']
 for t in timelines.values():t['state_at_first']=t['state_at_last']='UNANCHORED';t['depth_reconstruction']='NO_FULL_BOOK_ANCHOR';t['ordering']='UNQUALIFIED_RECEIVE_TIES' if t['receive_ties'] else 'NO_VERIFIED_SEQUENCE'
 assert not any(t['book_anchors'] for t in timelines.values())
 result={'events_source':len(rows),'token_timelines':list(timelines.values()),'state_at_T_proven':False,'full_depth_available_in_sample':False,'comparison':'NO_LOCAL_OVERLAP; all pairwise matching metrics remain null, never zero','historical_verdict':'NEW_24H_CAUSAL_CAPTURE_REQUIRED','scope':'This bounded accessible sample fails qualification; no assertion that every provider record lacks depth.'}
 (OUT/'HISTORICAL_TIMELINE.json').write_text(json.dumps(result,indent=2)+'\n')
 # Only new metadata, links, journal framing and checkpoint overhead: synthetic fixtures.
 class Measure:
  session='overhead';seq=0
  def __init__(self):self.bytes={};self.counts={};self.raw_bytes=0
  def append(self,bucket,payload,**kw):
   raw=json.dumps({'session':self.session,'seq':self.seq,'previous':'0'*64,'bucket':bucket,'payload':payload},sort_keys=True,separators=(',',':')).encode()
   self.bytes[bucket]=self.bytes.get(bucket,0)+36+len(zlib.compress(raw,1));self.counts[bucket]=self.counts.get(bucket,0)+1;self.seq+=1;return self.seq-1
 m=Measure();b=BookCapture(m);b.activate('fixture','condition',{'UP':'up','DOWN':'down'},1000000)
 initial=[dict(event_type='book',asset_id=token,timestamp='100',hash=token,bids=[{'price':'.49','size':'100'}],asks=[{'price':str(.5+i*.001),'size':'100'} for i in range(50)]) for token in ('up','down')]
 b.ingest(initial,101);start=time.perf_counter()
 for i in range(1000):
  ts=102+i;b.ingest({'event_type':'price_change','timestamp':str(ts),'price_changes':[{'asset_id':'up','price':'.5','size':str(100+i%7),'side':'SELL','hash':str(i)}]},ts+1)
 elapsed=time.perf_counter()-start
 from analysis.d6.causal_capture_24h_v1.collector import Observer
 obs=Observer(m,lambda:5000)
 for i in range(1000):
  obs('SIGNAL',{'signal_ts':i,'side':'UP','move':.001});obs('ENTRY_INTENT',{'signal_ts':i,'side':'UP'});obs('ENTRY_BOOK',{'signal_ts':i,'side':'UP','snapshot':b.latest});obs('ENTRY_CALC',{'signal_ts':i,'side':'UP','budget':25})
  obs('FILL_LEVEL',{'price':.5,'available':100,'take':50});obs('ENTRY_RESULT',{'signal_ts':i,'shares':50,'cost':25});obs('EXIT_WAIT',{'signal_ts':i,'side':'UP'});obs('EXIT_BOOK',{'signal_ts':i,'side':'UP','snapshot':b.latest});obs('EXIT_CALC',{'signal_ts':i,'shares':50});obs('FILL_LEVEL',{'price':.49,'available':100,'take':50});obs('EXIT_RESULT',{'signal_ts':i,'remaining':0,'sold':50,'proceeds':24.5})
 m.append('CHECKPOINT',{'previous_seq':m.seq-1,'previous_hash':'0'*64,'state':{'latest_book_refs':b.states,'pending_opportunities':obs.opportunities},'resume_live_allowed':False})
 # Measure actual framed file/fsync cost for *new* metadata only, no old raw archive benchmark.
 path=OUT/'OVERHEAD_NEW_METADATA.frames';j=Journal(path,'overhead_disk');started=time.perf_counter()
 for i in range(1000):j.append('BOOK_META',{'kind':'fixture_new_metadata','state_id':str(i),'raw_seq':i,'view_sha256':hashlib.sha256(str(i).encode()).hexdigest(),'depth_reference':'canonical_RAW'})
 j.checkpoint({'fixture':True});j.close();disk_seconds=time.perf_counter()-started
 overhead={'fixture_only':True,'market_payloads':1001,'opportunities':1000,'bytes_by_bucket':m.bytes,'records_by_bucket':m.counts,'metadata_bytes_per_state':m.bytes['BOOK_META']/m.counts['BOOK_META'],'causal_bytes_per_opportunity':m.bytes['CAUSAL']/1000,'normalize_plus_metadata_fixture_seconds':elapsed,'new_metadata_disk_records':1000,'new_metadata_disk_bytes':path.stat().st_size,'new_metadata_disk_seconds':disk_seconds,'raw_archive_benchmark_repeated':False,'realtime_capacity_proven':False,'projection':'Not a traffic-rate bound. Hard bucket byte caps plus margin independently bound disk usage; cap hit makes capture incomplete.'}
 (OUT/'OBSERVATION_OVERHEAD.json').write_text(json.dumps(overhead,indent=2)+'\n')
 (OUT/'STORAGE_PREFLIGHT.json').write_text(json.dumps(storage_preflight(shutil.disk_usage(ROOT).free),indent=2)+'\n')
 seal=source_seal(ROOT);(OUT/'SOURCE_HASHES.json').write_text(json.dumps({'hashes':seal.hashes,'seal_sha256':seal.hash},indent=2)+'\n')
 print(json.dumps({'storage':storage_preflight(shutil.disk_usage(ROOT).free),'overhead':overhead},indent=2))
if __name__=='__main__':main()
