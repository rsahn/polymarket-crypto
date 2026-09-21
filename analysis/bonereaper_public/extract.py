from fetch_public import get,ROOT
import datetime,json,time,collections
ADDR='0xeebde7a0e019a63e6b476eb425505b7b3e6eba30'
allrows=[];windows=[]
def window(a,b):
 label=f'activity_{a}_{b}'
 rows=get(label,'https://data-api.polymarket.com/activity',{'user':ADDR,'limit':500,'start':a,'end':b,'sortBy':'TIMESTAMP','sortDirection':'ASC'})
 if not isinstance(rows,list):raise RuntimeError(rows)
 if any(not a<=r['timestamp']<=b or r['proxyWallet'].lower()!=ADDR for r in rows):raise RuntimeError('filter not honored')
 if len(rows)>=500:
  if a==b:raise RuntimeError('second saturated: pagination required')
  mid=(a+b)//2;window(a,mid);window(mid+1,b);return
 windows.append({'start':a,'end':b,'rows':len(rows),'raw':label+'.body'})
 for i,r in enumerate(rows):allrows.append({**r,'_raw_file':label+'.body','_raw_index':i})
 time.sleep(.12)
for day in range(12,20):
 start=int(datetime.datetime(2026,9,day,tzinfo=datetime.timezone.utc).timestamp())
 window(start,start+86400-1)
 print('day',day,'total',len(allrows),'windows',len(windows),flush=True)
(ROOT/'activity_extracted.json').write_text(json.dumps(allrows),encoding='utf-8')
(ROOT/'coverage.json').write_text(json.dumps({'address':ADDR,'analysis_start_utc':'2026-09-13T00:00:00Z','analysis_end_utc':'2026-09-20T00:00:00Z','extra_leading_day':'2026-09-12','windows':windows,'extraction_rows':len(allrows),'types':dict(collections.Counter(r['type'] for r in allrows))},indent=2),encoding='utf-8')
print('TYPES',collections.Counter(r['type'] for r in allrows))
btc=[r for r in allrows if r['slug'].startswith(('btc-updown-5m-','btc-updown-15m-'))]
print('BTC',len(btc),'markets',len(set(r['conditionId'] for r in btc)))
