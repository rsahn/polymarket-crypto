"""Bounded public Parquet sample, no strategy or PnL."""
import io,json,urllib.request,hashlib,zlib
from pathlib import Path
URL='https://archive.pendulumflow.com/pmxt/v2/polymarket_orderbook_2026-08-09T23.parquet'
class Ranges(io.RawIOBase):
 def __init__(self,url,size,budget=32*1024**2):self.url=url;self.size=size;self.pos=0;self.budget=budget;self.total=0;self.requests=[]
 def readable(self):return True
 def seekable(self):return True
 def tell(self):return self.pos
 def seek(self,offset,whence=0):
  self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
  if self.pos<0:raise ValueError('NEGATIVE_SEEK')
  return self.pos
 def read(self,n=-1):
  n=min(self.size-self.pos,n if n>=0 else self.size-self.pos)
  if n<=0:return b''
  if self.total+n>self.budget:raise ValueError('SAMPLE_BYTE_BUDGET')
  start=self.pos;end=start+n-1
  req=urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{end}'})
  with urllib.request.urlopen(req,timeout=20) as r:
   if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{self.size}':raise ValueError('RANGE_NOT_HONORED')
   data=r.read(n+1)
  if len(data)!=n:raise ValueError('RANGE_SIZE')
  self.total+=n;self.pos+=n;self.requests.append({'start':start,'end':end,'sha256':hashlib.sha256(data).hexdigest()});return data
 def readinto(self,b):
  d=self.read(len(b));b[:len(d)]=d;return len(d)
def main():
 import pyarrow.parquet as pq
 out=Path(__file__).parent/'evidence';source=Ranges(URL,507501824);result={'url':URL,'max_transfer_bytes':source.budget,'max_rows':4096,'events_local':None,'overlap':'None: local full-depth captures start September20; sample August09','matched_events':None,'missing_source_events':None,'missing_local_events':None,'best_bid_match':None,'best_ask_match':None,'depth_match':None,'timestamp_delta_ms':None,'ordering_match':None,'token_match':None,'market_match':None};rows=[]
 try:
  p=pq.ParquetFile(source);result['schema']=str(p.schema_arrow);result['row_groups']=p.num_row_groups
  for batch in p.iter_batches(batch_size=1024,row_groups=[0],use_threads=False):
   for row in batch.to_pylist():
    rows.append({k:(v.decode('ascii') if isinstance(v,bytes) else v.isoformat() if hasattr(v,'isoformat') else str(v) if v is not None and not isinstance(v,(str,int,float,bool,list,dict)) else v) for k,v in row.items()})
   if len(rows)>=4096:break
  result['sample_obtained']=bool(rows);result['events_source']=len(rows)
  tokens={};ties=0;books=0
  for row in rows:
   key=(row.get('market'),row.get('asset_id'));previous=tokens.get(key)
   if previous and previous==row.get('timestamp_received'):ties+=1
   tokens[key]=row.get('timestamp_received');books+=row.get('event_type')=='book'
  result.update(distinct_market_tokens=len(tokens),same_token_receive_timestamp_ties=ties,book_snapshot_rows=books)
  result['reconstruction_verdict']='NOT_QUALIFIED: no original local decision clock or global tie-breaker; sample cannot establish 24h completeness'
 except Exception as e:result['error']=str(e);result['sample_obtained']=False
 encoded=json.dumps(rows,sort_keys=True,separators=(',',':')).encode();(out/'HISTORICAL_SAMPLE.json.zlib').write_bytes(zlib.compress(encoded))
 result.update(sample_sha256=hashlib.sha256(encoded).hexdigest(),transferred_bytes=source.total,range_requests=source.requests)
 (out/'HISTORICAL_BOOK_RECONSTRUCTION_TEST.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='range_requests'},indent=2))
if __name__=='__main__':main()
