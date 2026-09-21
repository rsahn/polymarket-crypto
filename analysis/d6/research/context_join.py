"""Contextual public activity join; strict backwards bounds, no inferred private inventory."""
import pathlib,json,sys,time,bisect,collections,math,hashlib
from offline import connect,save,pa,pq,D6,HERE

def pick_btc(ticks,times,bound,segment_start):
 for i in range(bisect.bisect_left(times,bound)-1,-1,-1):
  row=ticks[i];values=[row[k] for k in ('event_ts_ms','received_ts_ms','available_ts_ms')]
  if row['available_ts_ms']<segment_start or row['available_ts_ms']<bound-1000:return None
  if all(v is not None and bound-1000<=v<bound for v in values):return row
 return None

def select_context(c,valid):
 c.register('actions',pa.Table.from_pylist(valid))
 times=('event_ts_ms','received_ts_ms','available_ts_ms','up_source_ms','up_received_ms','down_source_ms','down_received_ms')
 requirements=' AND '.join('f.'+k+' IS NOT NULL AND f.'+k+'>=a.bound_ms-1000 AND f.'+k+'<a.bound_ms' for k in times)
 query='''SELECT a.action_id,a.bound_ms,a.outcome,a.quantity,a.split,f.* FROM actions a JOIN book_features f
 ON a.condition_id=f.condition_id AND a.market_slug=f.market_slug AND a.market_duration=f.market_duration
 AND a.active_generation=f.generation AND f.available_ts_ms>=a.activation_ms AND a.bound_ms<f.expiry_ts_ms
 AND a.token_id=CASE WHEN upper(a.outcome)='UP' THEN f.token_up ELSE f.token_down END
 WHERE '''+requirements+''' QUALIFY row_number() OVER(PARTITION BY a.action_id ORDER BY f.available_ts_ms DESC,f.event_id DESC)=1'''
 return c.execute(query).fetch_arrow_table().to_pylist()

def correlation(pairs):
 pairs=[(float(x),float(y)) for x,y in pairs if x is not None and y is not None]
 if len(pairs)<3:return {'n':len(pairs),'pearson':None}
 mx=sum(x for x,y in pairs)/len(pairs);my=sum(y for x,y in pairs)/len(pairs)
 xx=sum((x-mx)**2 for x,y in pairs);yy=sum((y-my)**2 for x,y in pairs)
 return {'n':len(pairs),'pearson':sum((x-mx)*(y-my) for x,y in pairs)/math.sqrt(xx*yy) if xx and yy else None}

def run(data,out):
 start=time.monotonic();out.mkdir(exist_ok=False);c=connect(data)
 plan=json.loads((HERE/'SPLIT_LOCK.json').read_text());splits={r['market_slug']:r['split'] for r in plan['markets']}
 raw=json.loads((D6/'bonereaper_contemporary/activity_normalized.json').read_text())
 activities=[{**r,'action_id':i,'bound_ms':r['bin_start_ms']-plan['bonereaper_time_budget_ms'],'split':splits.get(r['market_slug'],'OUTSIDE')} for i,r in enumerate(raw) if r['identity_verified'] and r['window_class']=='INTERIOR' and r['side']=='BUY' and r['type']=='TRADE' and splits.get(r['market_slug']) in ('TRAIN','VALIDATION')]
 controls=c.execute("SELECT available_ts_ms,event_id,kind,condition_id,generation,market_duration FROM events WHERE kind NOT IN ('BOOK','BTC') ORDER BY available_ts_ms,event_id").fetchall()
 valid=[];unmatched=[]
 for a in activities:
  known=[v for v in controls if v[0]<a['bound_ms'] and v[5]==a['market_duration'] and v[2] in ('ACTIVATE','RECONNECT','EXPIRE','SESSION_END','STALE_BOOK_RECONNECT','FORCED_RECONNECT_TEST','ROTATED','WS_ERROR')]
  if not known or known[-1][2]!='ACTIVATE' or known[-1][3]!=a['condition_id']:
   unmatched.append({'action_id':a['action_id'],'reason':'NO_ACTIVE_MATCHING_GENERATION'});continue
  a['active_generation']=known[-1][4];a['activation_ms']=known[-1][0];valid.append(a)
 if not valid:save(out/'JOIN_REPORT.json',{'matched':0,'eligible':len(activities),'reason':'NO_ACTIVE_GENERATIONS'});return
 rows=select_context(c,valid);btc=pq.read_table(data/'parquet/btc.parquet').to_pylist();btimes=[r['available_ts_ms'] for r in btc]
 for r in rows:
  btc_control=[v for v in controls if v[0]<r['bound_ms'] and v[2] in ('BTC_CONNECTED','BTC_RECONNECT')]
  segment=btc_control[-1][0] if btc_control and btc_control[-1][2]=='BTC_CONNECTED' else r['bound_ms']
  current=pick_btc(btc,btimes,r['bound_ms'],segment);r['btc_provenance']=current;r['inventory_initial']='UNKNOWN';r['context_only']=True
  for lag in (250,500,1000,3000,5000,10000,15000,30000):
   prior=pick_btc(btc,btimes,r['bound_ms']-lag,segment);r['btc_return_'+str(lag)]=current['price']/prior['price']-1 if current and prior else None;r['btc_lag_provenance_'+str(lag)]=prior
 save(out/'JOINED_CONTEXT.json',rows)
 matched={r['action_id'] for r in rows};unmatched.extend({'action_id':a['action_id'],'reason':'NO_FRESH_CAUSAL_BOOK'} for a in valid if a['action_id'] not in matched)
 groups={}
 for duration in ('5m','15m'):
  for split in ('TRAIN','VALIDATION'):
   rr=[r for r in rows if r['market_duration']==duration and r['split']==split];momentum=[r for r in rr if r['btc_return_5000'] is not None and r['btc_return_5000']!=0]
   cheaper=[r for r in rr if r['up_ask'] is not None and r['down_ask'] is not None and r['up_ask']!=r['down_ask']]
   micro=[r for r in rr if r['up_imbalance'] is not None and r['down_imbalance'] is not None and r['up_imbalance']!=r['down_imbalance']]
   groups[duration+'_'+split]={'operations':len(rr),'markets':len({r['market_slug'] for r in rr}),'H4_momentum_side_agreement':sum((r['btc_return_5000']>0)==(r['outcome'].upper()=='UP') for r in momentum)/len(momentum) if momentum else None,'H4_n':len(momentum),'cheaper_side_agreement':sum((r['up_ask']<r['down_ask'])==(r['outcome'].upper()=='UP') for r in cheaper)/len(cheaper) if cheaper else None,'H5_microstructure_side_agreement':sum((r['up_imbalance']>r['down_imbalance'])==(r['outcome'].upper()=='UP') for r in micro)/len(micro) if micro else None,'H7_age_thirds_counts':dict(collections.Counter('BEFORE' if r['market_age_seconds']<0 else min(2,int(r['market_age_seconds']/(100 if duration=='5m' else 300))) for r in rr)),'H8_observed_quantity_mean':sum(r['quantity'] for r in rr)/len(rr) if rr else None}
 for group,g in groups.items():
  duration,split=group.split('_',1);rr=[r for r in rows if r['market_duration']==duration and r['split']==split]
  g['H8_size_context_correlations']={name:correlation([(r['quantity'],value(r)) for r in rr]) for name,value in {'absolute_btc_momentum':lambda r:abs(r['btc_return_5000']) if r['btc_return_5000'] is not None else None,'top_ask_qty':lambda r:r['up_ask_qty'] if r['outcome'].upper()=='UP' else r['down_ask_qty'],'time_remaining':lambda r:r['remaining_seconds']}.items()}
 save(out/'JOIN_REPORT.json',{'eligible':len(activities),'matched':len(rows),'unmatched':unmatched,'groups':groups,'H1_H2_H3_H6':'NON_IDENTIFIABLE_INITIAL_INVENTORY_UNKNOWN','H8_cash_inventory_policy':'NON_IDENTIFIABLE_PRIVATE_CASH_AND_INVENTORY','interpretation':'Descriptive contextual associations, clustered observations, no significance or edge claim; API time semantics not bounded to actual decision. Top-level imbalance only, not full-depth imbalance.','oos_opened':False,'time_budget_ms':100,'elapsed_seconds':time.monotonic()-start})
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--data',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();run(a.data,a.out)
