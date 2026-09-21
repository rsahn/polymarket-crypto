from fetch_public import get,ROOT
import json,time,datetime,csv,collections
markets=json.loads((ROOT/'markets.json').read_text(encoding='utf-8'));found={}
for i in range(0,len(markets),40):
 batch=markets[i:i+40]; params=[('closed','true'),('limit','100')]+[('condition_ids',m['condition_id']) for m in batch]
 rows=get(f'metadata_batch_{i:04d}','https://gamma-api.polymarket.com/markets',params)
 if not isinstance(rows,list):raise RuntimeError(rows)
 wanted={m['condition_id'] for m in batch}
 if any(r['conditionId'] not in wanted for r in rows):raise RuntimeError('filter ignored')
 for r in rows:found[r['conditionId']]=r
 if i%200==0:print('metadata',len(found),'/',len(markets),flush=True)
 time.sleep(.15)
(ROOT/'market_metadata.json').write_text(json.dumps(found),encoding='utf-8')
checks={'requested':len(markets),'found':len(found),'missing':[],'start_mismatch':[],'end_mismatch':[],'slug_mismatch':[],'token_mismatch':[],'trade_before_market_creation':[]}
for m in markets:
 r=found.get(m['condition_id'])
 if not r:checks['missing'].append(m['market_slug']);continue
 start=r.get('eventStartTime') or (r.get('events') or [{}])[0].get('startTime')
 if not start or int(datetime.datetime.fromisoformat(start.replace('Z','+00:00')).timestamp())!=m['market_open_timestamp']:checks['start_mismatch'].append(m['market_slug'])
 if int(datetime.datetime.fromisoformat(r['endDate'].replace('Z','+00:00')).timestamp())!=m['market_open_timestamp']+m['market_duration']:checks['end_mismatch'].append(m['market_slug'])
 if r['slug']!=m['market_slug']:checks['slug_mismatch'].append(m['market_slug'])
with (ROOT/'btc_inventory_ledger.csv').open(encoding='utf-8-sig') as f:
 for r in csv.DictReader(f):
  if r['type']!='TRADE' or r['condition_id'] not in found:continue
  md=found[r['condition_id']];mapping=dict(zip(json.loads(md['outcomes']),json.loads(md['clobTokenIds'])))
  if mapping.get(r['outcome'])!=r['token_id']:checks['token_mismatch'].append(r['record_id'])
  if float(r['timestamp'])<datetime.datetime.fromisoformat(md['createdAt'].replace('Z','+00:00')).timestamp():checks['trade_before_market_creation'].append(r['record_id'])
(ROOT/'metadata_validation.json').write_text(json.dumps(checks,indent=2),encoding='utf-8');print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in checks.items()}))
