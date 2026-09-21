"""Only public GET requests; contemporary extraction separate from historical study."""
import datetime,hashlib,json,pathlib,time,urllib.request,urllib.parse,re
HERE=pathlib.Path(__file__).resolve().parent;D6=HERE.parent;ROOT=D6.parents[1]
ADDRESS='0xeebde7a0e019a63e6b476eb425505b7b3e6eba30'
def fetch(label,url,params):
 raw=HERE/'raw';raw.mkdir(exist_ok=True);path=raw/(label+'.body');meta=raw/(label+'.meta.json')
 if path.exists():
  if not meta.exists():raise RuntimeError('UNVERIFIED_CACHED_RESPONSE')
  body=path.read_bytes()
  if hashlib.sha256(body).hexdigest()!=json.loads(meta.read_text())['sha256']:raise RuntimeError('RAW_HASH_MISMATCH')
  return json.loads(body)
 url+='?'+urllib.parse.urlencode(params)
 request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'},method='GET')
 for attempt in range(3):
  try:
   with urllib.request.urlopen(request,timeout=30) as response:body=response.read();status=response.status;headers=dict(response.headers)
   break
  except Exception:
   if attempt==2:raise
   time.sleep(2+attempt)
 with path.open('xb') as f:f.write(body)
 with meta.open('x',encoding='utf-8') as f:json.dump({'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':status,'headers':headers,'sha256':hashlib.sha256(body).hexdigest()},f,indent=2)
 return json.loads(body)
def main():
 manifest=json.loads((D6/'data/raw_manifest.json').read_text(encoding='utf-8'))
 status=json.loads((ROOT/'analysis/d5/24h_20260920_124822/status.json').read_text(encoding='utf-8'))
 begin=int(datetime.datetime.fromisoformat(status['collection_started_utc']).timestamp()*1000)
 stop=next(m['payload']['collection_stop_ts_ms'] for m in manifest['tail_markers'] if 'collection_stop_ts_ms' in m['payload'])
 rows=[];windows=[]
 def window(a,b):
  label=f'activity_{a}_{b}'
  batch=fetch(label,'https://data-api.polymarket.com/activity',{'user':ADDRESS,'limit':500,'start':a,'end':b,'sortBy':'TIMESTAMP','sortDirection':'ASC'})
  if not isinstance(batch,list):raise RuntimeError('INVALID_ACTIVITY_RESPONSE')
  if any(not a<=r['timestamp']<=b or r.get('proxyWallet','').lower()!=ADDRESS for r in batch):raise RuntimeError('API_FILTER_NOT_HONORED')
  if len(batch)>=500:
   if a==b:raise RuntimeError('SATURATED_SECOND_NEEDS_PAGINATION')
   middle=(a+b)//2;window(a,middle);window(middle+1,b);return
  windows.append({'start':a,'end':b,'rows':len(batch),'raw':label+'.body'})
  for index,r in enumerate(batch):rows.append({**r,'_raw_file':label+'.body','_raw_index':index})
  print('public_rows',len(rows),'windows',len(windows),flush=True)
 window(begin//1000,stop//1000)
 raw_rows=rows;seen=set();dedup=[];duplicates=[]
 for row in rows:
  key=json.dumps({k:v for k,v in row.items() if not k.startswith('_')},sort_keys=True)
  if key in seen:duplicates.append(row);continue
  seen.add(key);dedup.append(row)
 conditions=sorted({r.get('conditionId') for r in dedup if r.get('slug','').startswith(('btc-updown-5m-','btc-updown-15m-')) and r.get('conditionId')})
 markets={}
 for c in conditions:
  items=fetch('market_'+c,'https://gamma-api.polymarket.com/markets',{'condition_ids':c,'closed':'true'})
  if isinstance(items,list):
   for item in items:
    if item.get('conditionId')==c:markets[c]=item
 normalized=[]
 for row in dedup:
  slug=row.get('slug','');match=re.fullmatch(r'btc-updown-(5m|15m)-\d+',slug)
  if not match:continue
  metadata=markets.get(row.get('conditionId'));identity_ok=False
  if metadata:
   tokens=metadata.get('clobTokenIds',[]);outcomes=metadata.get('outcomes',[])
   if isinstance(tokens,str):tokens=json.loads(tokens)
   if isinstance(outcomes,str):outcomes=json.loads(outcomes)
   mapping={str(o).upper():str(t) for o,t in zip(outcomes,tokens)}
   identity_ok=metadata.get('slug')==slug and (row.get('type')!='TRADE' or mapping.get(str(row.get('outcome')).upper())==str(row.get('asset')))
  t=row['timestamp']*1000
  normalized.append({'condition_id':row.get('conditionId'),'token_id':row.get('asset'),'market_slug':slug,'market_duration':match[1],'timestamp_s':row['timestamp'],'bin_start_ms':t,'bin_end_ms':t+1000,'window_class':'INTERIOR' if t>=begin and t+1000<=stop else 'BOUNDARY_AMBIGUOUS','outcome':row.get('outcome'),'side':row.get('side'),'price':row.get('price'),'quantity':row.get('size'),'usdcSize':row.get('usdcSize'),'transaction_hash':row.get('transactionHash'),'type':row.get('type'),'identity_verified':identity_ok,'inventory_initial':'UNKNOWN','raw_file':row['_raw_file'],'raw_index':row['_raw_index']})
 outputs={'activity_raw_extracted.json':raw_rows,'activity_normalized.json':normalized,'duplicates.json':duplicates,'market_metadata.json':markets,'coverage.json':{'address':ADDRESS,'begin_ms':begin,'end_ms':stop,'windows':windows,'raw_rows':len(raw_rows),'unique_rows':len(dedup),'btc_rows':len(normalized),'inventory_initial':'UNKNOWN','margin_seconds':0,'api_second_precision_preserved':True,'identity_unverified':sum(not r['identity_verified'] for r in normalized)}}
 for name,data in outputs.items():
  with (HERE/name).open('x',encoding='utf-8') as f:json.dump(data,f,indent=2)
 print(json.dumps(outputs['coverage.json']),flush=True)
if __name__=='__main__':main()
