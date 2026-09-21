"""D6 deterministic chronological replay over derived Parquet only; never reads RAW SQLite."""
import sys,pathlib,json,time,zlib,hashlib,random,math,collections,shutil
HERE=pathlib.Path(__file__).resolve().parent;D6=HERE.parent
sys.path[:0]=[str(D6/'vendor'),str(D6/'paper_runtime')]
import duckdb,pyarrow as pa,pyarrow.parquet as pq
from engine import Engine,Limits,D,encode

def decode(v):
 if isinstance(v,bytes):
  try:v=zlib.decompress(v)
  except zlib.error:pass
 return json.loads(v)
def save(p,v):p.write_text(json.dumps(v,default=str,indent=2,allow_nan=False),encoding='utf-8')
def connect(data):
 c=duckdb.connect();c.execute("SET memory_limit='384MB'");c.execute('SET threads=1');c.execute("SET preserve_insertion_order=false")
 for name in ('events','markets','book_sides','book_features','btc'):
  path=str(data/'parquet'/f'{name}.parquet').replace("'","''");c.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
 return c

def baseline(name,e,key,t):
 if name=='D6':return e.decide(key,t)
 f=e.features(key,t);wait={'action':'WAIT','reason':name,'features':f}
 if not f or e.pending or t-e.last_action.get(key,-10**12)<e.limits.action_interval_ms:return wait
 if name=='WAIT_ONLY':return wait
 if name=='RANDOM_SIDE':side='UP' if int(hashlib.sha256(f'{key}:{t}:seed42'.encode()).hexdigest()[:8],16)%2 else 'DOWN'
 elif name=='ALWAYS_CHEAPER_SIDE':side='UP' if f['up_ask'] is not None and f['down_ask'] is not None and f['up_ask']<=f['down_ask'] else 'DOWN'
 elif name=='ALWAYS_REBALANCE':side='UP' if e.positions[key].up<=e.positions[key].down else 'DOWN'
 elif name=='FIXED_ALTERNATING':side='UP' if sum(o['condition_id']==key for o in e.orders)%2==0 else 'DOWN'
 elif name=='PAIR_COST_THRESHOLD':
  if f['pair_ask_cost'] is None or f['pair_ask_cost']>=D('.98'):return wait
  side='UP' if e.positions[key].up<=e.positions[key].down else 'DOWN'
 else:raise ValueError(name)
 if f[side.lower()+'_spread'] is None or f[side.lower()+'_spread']>D('.04') or f[side.lower()+'_depth']<D(5):return wait
 return {'action':'BUY_'+side,'reason':name,'features':f}

def execute(data,out,reuse_books=None):
 start=time.monotonic();plan=json.loads((HERE/'SPLIT_LOCK.json').read_text());expected=(HERE/'SPLIT_LOCK.sha256').read_text().strip()
 if hashlib.sha256((HERE/'SPLIT_LOCK.json').read_bytes()).hexdigest()!=expected:raise RuntimeError('SPLIT_LOCK_CHANGED')
 if json.loads((data/'progress.json').read_text())['status']!='COMPLETE':raise RuntimeError('CONVERSION_NOT_COMPLETE')
 out.mkdir(exist_ok=False);c=connect(data)
 allowed=[r for r in plan['markets'] if r['market_duration']=='5m' and r['split'] in ('TRAIN','VALIDATION')]
 dest=out/'replay_books.parquet'
 if reuse_books is not None:
  shutil.copyfile(reuse_books,dest)
 else:
  c.register('allowed',pa.Table.from_pylist(allowed))
  # FIRST snapshot per 100ms bucket, timestamp retained exactly. Each bucket can be selected online.
  c.execute('''CREATE TEMP TABLE chosen AS SELECT min(e.event_id) event_id FROM events e JOIN allowed a USING(condition_id,market_slug)
  WHERE e.kind='BOOK' AND e.available_ts_ms>=a.start_ms AND e.available_ts_ms<a.expiry_ts_ms
  GROUP BY e.condition_id,e.available_ts_ms//100''')
  dest=out/'replay_books.parquet'
  sql='''SELECT e.*,m.expiry_ts_ms,a.split,u.event_ts_ms up_source,u.received_ts_ms up_receive,u.token_id up_token,u.best_bid up_bid,u.best_ask up_ask,u.bids_json up_bids,u.asks_json up_asks,
  d.event_ts_ms down_source,d.received_ts_ms down_receive,d.token_id down_token,d.best_bid down_bid,d.best_ask down_ask,d.bids_json down_bids,d.asks_json down_asks
  FROM chosen k JOIN events e USING(event_id) JOIN markets m USING(condition_id,market_slug) JOIN allowed a USING(condition_id,market_slug)
  JOIN book_sides u ON u.event_id=e.event_id AND u.side='UP' JOIN book_sides d ON d.event_id=e.event_id AND d.side='DOWN' ORDER BY e.event_id'''
  shards=out/'book_shards';shards.mkdir();maximum=c.execute('SELECT max(event_id) FROM chosen').fetchone()[0] or 0
  for lo in range(1,maximum+1,100000):
   hi=min(maximum,lo+99999);bounded=sql.replace('FROM chosen k',f'FROM (SELECT * FROM chosen WHERE event_id BETWEEN {lo} AND {hi}) k').replace('JOIN events e',f'JOIN (SELECT * FROM events WHERE event_id BETWEEN {lo} AND {hi}) e')
   for side in ('u','d'):bounded=bounded.replace('JOIN book_sides '+side,f'JOIN (SELECT * FROM book_sides WHERE event_id BETWEEN {lo} AND {hi}) '+side)
   shard=shards/f'{lo:09d}.parquet';c.execute("COPY ("+bounded+") TO '"+str(shard).replace("'","''")+"' (FORMAT PARQUET,COMPRESSION ZSTD)")
   save(out/'progress.json',{'status':'RUNNING','stage':'EXTRACT_REPLAY_BOOKS','event_id_through':hi,'event_id_max':maximum,'percent':100*hi/maximum,'elapsed_seconds':time.monotonic()-start})
  c.execute("COPY (SELECT * FROM read_parquet('"+str(shards/'*.parquet').replace("'","''")+"') ORDER BY event_id) TO '"+str(dest).replace("'","''")+"' (FORMAT PARQUET,COMPRESSION ZSTD)")
 btc=pq.read_table(data/'parquet/btc.parquet').to_pylist()
 controls=c.execute("SELECT event_id,kind,available_ts_ms,condition_id,generation,market_duration FROM events WHERE kind NOT IN ('BOOK','BTC') ORDER BY event_id").fetchall()
 models=[('D6',v) for v in (0,100,250,500)]+[(n,250) for n in ('RANDOM_SIDE','ALWAYS_CHEAPER_SIDE','ALWAYS_REBALANCE','FIXED_ALTERNATING','PAIR_COST_THRESHOLD','WAIT_ONLY')]
 reports={};total=pq.ParquetFile(dest).metadata.num_rows;done=0
 for split in ('TRAIN','VALIDATION'):
  engines={(n,l):Engine(Limits(latency_ms=l)) for n,l in models};timers={};bi=ci=0;active={};lastt=0;stopped={};digests={k:hashlib.sha256() for k in engines}
  for batch in pq.ParquetFile(dest).iter_batches(batch_size=1000):
   for row in batch.to_pylist():
    if row['split']!=split:continue
    t=row['available_ts_ms'];lastt=t
    while ci<len(controls) and controls[ci][0]<row['event_id']:
     eid,kind,ct,key,generation,duration=controls[ci];ci+=1
     if duration=='5m' and kind in ('ACTIVATE','RECONNECT','EXPIRE','SESSION_END','STALE_BOOK_RECONNECT','FORCED_RECONNECT_TEST','WS_ERROR'):
      for e in engines.values():e.books.clear()
      active=({key:generation} if kind=='ACTIVATE' else {})
     if kind in ('BTC_DISCONNECTED','BTC_ERROR','BTC_RECONNECT','BTC_CONNECTED'):
      for e in engines.values():e.btc.clear()
    while bi<len(btc) and btc[bi]['event_id']<row['event_id']:
     b=btc[bi];bi+=1
     for e in engines.values():e.tick(b['price'],b['event_ts_ms'],b['received_ts_ms'],b['available_ts_ms'])
    identity={k:row[k] for k in ('condition_id','market_slug','market_duration','token_up','token_down','expiry_ts_ms')}
    snapshot={**identity,'event_ts_ms':row['event_ts_ms'],'received_ts_ms':row['received_ts_ms']}
    for side in ('up','down'):
     snapshot[side]={'token_id':row[side+'_token'],'event_ts_ms':row[side+'_source'],'received_ts_ms':row[side+'_receive'],'bid':row[side+'_bid'],'ask':row[side+'_ask'],'bids':decode(row[side+'_bids']),'asks':decode(row[side+'_asks'])}
    key=row['condition_id']
    if active.get(key)!=row['generation']:continue
    for model,e in engines.items():
     if model in stopped:continue
     e.observe(identity,snapshot,t);e.execute_due(t)
     if t-timers.get(model,0)>=1000:
      timers[model]=t;decision=baseline(model[0],e,key,t);digests[model].update(encode({'event_id':row['event_id'],'decision':decision}).encode());e.submit(key,decision,t)
      if model[1]==0:e.execute_due(t)
      risk=e.state(t)
      if risk['max_drawdown_lower_bound_valuation']>D(e.limits.max_drawdown):
       if e.pending:e.pending['status']='CANCELLED_ON_DRAWDOWN';e.pending=None;e.reserved=D(0)
       stopped[model]={'timestamp_ms':t,'reason':'MAX_PAPER_DRAWDOWN','account':e.state(t)}
    done+=1
    if done%1000==0:save(out/'progress.json',{'status':'RUNNING','stage':split,'book_rows_processed':done,'book_rows_total':total,'percent':100*done/total,'elapsed_seconds':time.monotonic()-start})
  reports[split]={}
  for model,e in engines.items():
   if e.pending:e.pending['status']='CANCELLED_AT_SPLIT_END';e.pending=None;e.reserved=D(0)
   result=stopped[model]['account'] if model in stopped else e.state(lastt);result['risk_stop']={k:v for k,v in stopped[model].items() if k!='account'} if model in stopped else None;result['decisions_sha256']=digests[model].hexdigest();result['execution_sha256']=hashlib.sha256(encode(e.orders).encode()).hexdigest();reports[split][model[0]+'_'+str(model[1])]=result
 save(out/'OFFLINE_COMPARISON.json',{'results':reports,'oos_opened':False,'initial_virtual_inventory':'ZERO separately for each simulated portfolio/split; NOT Bonereaper inventory','settlement':'No contemporaneous verified resolution in dataset: none fabricated; capital remains locked','book_sampling':'first snapshot per100ms, original timestamps; conservative incomplete liquidity refresh; execution first sampled BOOK at/after arrival','limitations':['Historical policy evaluations are exploratory','No claim of profit/edge if equity unresolved','Short sample and market dependence','Runtime settling behavior separately tested, not inferred from expiry'],'elapsed_seconds':time.monotonic()-start})
 save(out/'progress.json',{'status':'COMPLETE','rows':done,'total':total,'elapsed_seconds':time.monotonic()-start})
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--data',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--reuse-books',type=pathlib.Path);a=p.parse_args();execute(a.data,a.out,a.reuse_books)
