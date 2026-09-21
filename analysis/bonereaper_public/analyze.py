from pathlib import Path
import json,csv,collections,re,hashlib,statistics,datetime,math
ROOT=Path(__file__).resolve().parent
START=1789257600 # 2026-09-13 UTC
END=1789862400 # 2026-09-20 UTC, exclusive
PAT=re.compile(r'^btc-updown-(5m|15m)-(\d+)$')
def iso(t): return datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
def dump(name,obj): (ROOT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def csvout(name,rows):
 if not rows:return
 with (ROOT/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def dist(v):
 v=sorted(v)
 if not v:return {'n':0}
 def q(p):
  x=p*(len(v)-1);i=int(x);return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(x-i)
 return {'n':len(v),'min':v[0],'p05':q(.05),'p25':q(.25),'median':q(.5),'mean':statistics.mean(v),'p75':q(.75),'p95':q(.95),'max':v[-1]}
def key(r):return tuple(str(r.get(k,'')) for k in ('proxyWallet','transactionHash','timestamp','conditionId','type','asset','side','outcome','size','price','usdcSize'))
def reconstruct(rs):
 q={'Up':0.,'Down':0.};c={'Up':0.,'Down':0.};reported={'Up':0.,'Down':0.};cash=0.;grosscash=0.;unknown=False;ledger=[];last_pre_settlement=None
 ties=collections.Counter(r['timestamp'] for r in rs)
 for r in rs:
  typ=r['type'];out=r['outcome'];qty=float(r['quantity']);price=float(r['price']);notional=float(r['notional']);reported_cash=float(r['reported_usdc']);flag='conditional_zero_opening_no_unseen_transfers'
  if typ=='TRADE':
   sign=1 if r['side']=='BUY' else -1
   cash-=sign*reported_cash;grosscash-=sign*notional
   if not unknown:
    if sign==1:q[out]+=qty;c[out]+=notional;reported[out]+=reported_cash
    elif qty>q[out]+1e-6:unknown=True;flag='sell_exceeds_observed_inventory'
    else:
     av=c[out]/q[out] if q[out] else 0;ac=reported[out]/q[out] if q[out] else 0
     q[out]-=qty;c[out]-=qty*av;reported[out]-=qty*ac
  elif typ=='MERGE':
   cash+=reported_cash;grosscash+=qty
   if not unknown:
    if qty>min(q.values())+1e-6:unknown=True;flag='merge_exceeds_observed_inventory'
    else:
     for side in q:
      av=c[side]/q[side] if q[side] else 0;ac=reported[side]/q[side] if q[side] else 0
      q[side]-=qty;c[side]-=qty*av;reported[side]-=qty*ac
  elif typ=='SPLIT':
   cash-=reported_cash;grosscash-=qty;unknown=True;flag='split_cost_allocation_unknown'
  elif typ=='REDEEM':cash+=reported_cash;unknown=True;flag='post_redeem_token_burns_not_reconstructed'
  else:unknown=True;flag='unsupported_inventory_event'
  if unknown:
   state={k:None for k in ['up_qty','down_qty','up_cost_basis','down_cost_basis','average_up_cost','average_down_cost','paired_qty','directional_up','directional_down','paired_cost_basis','average_pair_cost','average_pair_cost_reported','inventory_imbalance','imbalance_shares']}
  else:
   u,d=q['Up'],q['Down'];au=c['Up']/u if u else None;ad=c['Down']/d if d else None;paired=min(u,d);ap=(au+ad) if paired>1e-9 else None
   arp=(reported['Up']/u+reported['Down']/d) if paired>1e-9 else None
   state={'up_qty':u,'down_qty':d,'up_cost_basis':c['Up'],'down_cost_basis':c['Down'],'average_up_cost':au,'average_down_cost':ad,'paired_qty':paired,'directional_up':max(u-d,0),'directional_down':max(d-u,0),'paired_cost_basis':paired*ap if ap is not None else 0,'average_pair_cost':ap,'average_pair_cost_reported':arp,'inventory_imbalance':(u-d)/(u+d) if u+d else 0,'imbalance_shares':u-d}
  row={**r,**state,'cash_flow_reported':cash,'cash_flow_gross_trades_merges':grosscash,'inventory_status':flag if not unknown or flag!='conditional_zero_opening_no_unseen_transfers' else 'unknown_after_prior_event','same_second_rows':ties[r['timestamp']],'intra_second_order':'UNKNOWN' if ties[r['timestamp']]>1 else 'single_row'}
  ledger.append(row)
 return ledger

def main():
 raw=json.loads((ROOT/'activity_extracted.json').read_text(encoding='utf-8'))
 seen=set();unique=[];dupes=[]
 for r in raw:
  k=key(r)
  if k in seen:dupes.append(r);continue
  seen.add(k);unique.append(r)
 dump('duplicate_candidates.json',dupes)
 operations=[]
 for r in unique:
  m=PAT.match(r.get('slug',''));duration=int(m[1][:-1])*60 if m else None;opened=int(m[2]) if m else None
  operations.append({'record_id':hashlib.sha256('|'.join(key(r)).encode()).hexdigest(),'timestamp':r['timestamp'],'timestamp_utc':iso(r['timestamp']),'market_slug':r['slug'],'condition_id':r['conditionId'],'market_duration':duration,'market_open_timestamp':opened,'type':r['type'],'outcome':r['outcome'],'side':r['side'],'price':r['price'],'quantity':r['size'],'notional':r['price']*r['size'] if r['type']=='TRADE' else r['usdcSize'],'reported_usdc':r['usdcSize'],'cash_minus_price_quantity':r['usdcSize']-r['price']*r['size'] if r['type']=='TRADE' else None,'token_id':r['asset'],'transaction_hash':r['transactionHash'],'proxy_wallet':r['proxyWallet'],'source':'https://data-api.polymarket.com/activity','raw_file':r['_raw_file'],'raw_index':r['_raw_index']})
 csvout('operations.csv',operations)
 groups=collections.defaultdict(list)
 for r in operations:
  if r['market_open_timestamp'] is not None and START<=r['market_open_timestamp']<END:groups[r['condition_id']].append(r)
 ledgers=[];markets=[];allbatches=[];transitions=[]
 for cond,rs in groups.items():
  rs.sort(key=lambda r:(r['timestamp'],r['raw_file'],r['raw_index']))
  fills=[r for r in rs if r['type']=='TRADE']
  if not fills:continue
  if any(r['outcome'] not in ('Up','Down') or r['side'] not in ('BUY','SELL') for r in fills):raise ValueError('invalid outcomes')
  ledger=reconstruct(rs);ledgers+=ledger;op=rs[0]['market_open_timestamp'];end=op+rs[0]['market_duration']
  # End-of-second states; no alleged exchange ordering among same-second records.
  batches=[]
  for t,lr in __import__('itertools').groupby(ledger,key=lambda r:r['timestamp']):
   lr=list(lr);tr=[r for r in lr if r['type']=='TRADE'];s=lr[-1]
   if tr and t<=end and s['paired_qty'] is not None:
    b={k:s[k] for k in ['timestamp','market_slug','condition_id','market_duration','up_qty','down_qty','paired_qty','average_pair_cost','average_pair_cost_reported','inventory_imbalance','imbalance_shares']}
    b.update({'trades_in_second':len(tr),'outcomes':','.join(sorted(set(r['outcome'] for r in tr))),'buy_qty_up':sum(r['quantity'] for r in tr if r['side']=='BUY' and r['outcome']=='Up'),'buy_qty_down':sum(r['quantity'] for r in tr if r['side']=='BUY' and r['outcome']=='Down')});batches.append(b)
  allbatches+=batches
  ordered=[b for b in batches if b['outcomes'] in ('Up','Down')]
  opp=[];updown=downup=0
  for prev,nxt in zip(batches,batches[1:]):
   if prev['outcomes'] in ('Up','Down') and nxt['outcomes'] in ('Up','Down') and prev['outcomes']!=nxt['outcomes']:
    dt=nxt['timestamp']-prev['timestamp'];opp.append(dt);updown+=prev['outcomes']=='Up';downup+=prev['outcomes']=='Down'
    transitions.append({'condition_id':cond,'market_duration':rs[0]['market_duration'],'from':prev['outcomes'],'to':nxt['outcomes'],'seconds':dt})
  pairs=[b for b in batches if b['paired_qty']>1e-9]
  last=batches[-1] if batches else None
  buys={s:sum(r['quantity'] for r in fills if r['side']=='BUY' and r['outcome']==s) for s in ('Up','Down')}
  under={}
  for cutoff in (1.,.99,.98,.95):
   duration=0.;qt=0.;pqt=0.;maxq=0.
   for i,b in enumerate(batches):
    stop=min(end,batches[i+1]['timestamp'] if i+1<len(batches) else end);dt=max(0,stop-max(op,b['timestamp']))
    if b['average_pair_cost'] is not None and b['average_pair_cost']<cutoff:
     duration+=dt;qt+=dt*b['paired_qty'];pqt+=dt*b['paired_qty']*b['average_pair_cost'];maxq=max(maxq,b['paired_qty'])
   under[str(cutoff)]={'seconds':duration,'paired_share_seconds':qt,'max_paired_qty':maxq,'qty_time_weighted_pair_cost':pqt/qt if qt else None}
  rebalance_eligible=rebalance_opposite=rebalance_reduces=0
  for prev,b in zip(batches,batches[1:]):
   imb=prev['imbalance_shares']
   if abs(imb)>1e-9 and b['buy_qty_up']+b['buy_qty_down']>0:
    rebalance_eligible+=1;rebalance_opposite+=(b['buy_qty_down']>0 if imb>0 else b['buy_qty_up']>0);rebalance_reduces+=abs(b['imbalance_shares'])<abs(imb)-1e-9
  markets.append({'condition_id':cond,'market_slug':rs[0]['market_slug'],'market_duration':rs[0]['market_duration'],'market_open_timestamp':op,'fills':len(fills),'buy_up_fills':sum(r['side']=='BUY' and r['outcome']=='Up' for r in fills),'buy_down_fills':sum(r['side']=='BUY' and r['outcome']=='Down' for r in fills),'sell_fills':sum(r['side']=='SELL' for r in fills),'both_outcomes_bought':all(v>0 for v in buys.values()),'first_leg':batches[0]['outcomes'] if batches else None,'first_fill_offset':fills[0]['timestamp']-op,'last_fill_offset':fills[-1]['timestamp']-op,'up_to_down':updown,'down_to_up':downup,'opposite_seconds':opp,'same_second_mixed_batches':sum(',' in b['outcomes'] for b in batches),'final_pre_expiry':last,'min_pair_cost':min((b['average_pair_cost'] for b in pairs),default=None),'min_pair_cost_reported':min((b['average_pair_cost_reported'] for b in pairs),default=None),'max_paired_qty':max((b['paired_qty'] for b in batches),default=0),'max_abs_imbalance_shares':max((abs(b['imbalance_shares']) for b in batches),default=0),'max_abs_normalized_imbalance':max((abs(b['inventory_imbalance']) for b in batches),default=0),'under_threshold':under,'rebalance_eligible':rebalance_eligible,'rebalance_opposite':rebalance_opposite,'rebalance_reduces':rebalance_reduces,'merges':sum(r['type']=='MERGE' for r in rs),'redeems':sum(r['type']=='REDEEM' for r in rs),'unknown_inventory_rows':sum(r['up_qty'] is None for r in ledger),'trades_after_expiry':sum(r['timestamp']>end for r in fills),'cash_reported_last':ledger[-1]['cash_flow_reported']})
 csvout('btc_inventory_ledger.csv',ledgers);csvout('btc_second_states.csv',allbatches);csvout('opposite_transitions.csv',transitions);dump('markets.json',markets)
 summary={}
 for seconds in (300,900):
  ms=[m for m in markets if m['market_duration']==seconds];fs=[r for r in ledgers if r['type']=='TRADE' and r['market_duration']==seconds];bs=[b for b in allbatches if b['market_duration']==seconds and b['average_pair_cost'] is not None];last=[m['final_pre_expiry'] for m in ms if m['final_pre_expiry'] and m['final_pre_expiry']['average_pair_cost'] is not None]
  summary[str(seconds)]={'markets':len(ms),'fills':len(fs),'types':dict(collections.Counter(r['side'] for r in fs)),'fills_per_market':dist([m['fills'] for m in ms]),'both_outcomes_markets':sum(m['both_outcomes_bought'] for m in ms),'both_outcomes_pct':100*sum(m['both_outcomes_bought'] for m in ms)/len(ms) if ms else None,'first_leg':dict(collections.Counter(m['first_leg'] for m in ms)),'up_to_down':sum(m['up_to_down'] for m in ms),'down_to_up':sum(m['down_to_up'] for m in ms),'opposite_seconds':dist([v for m in ms for v in m['opposite_seconds']]),'fill_quantity':dist([r['quantity'] for r in fs]),'fill_notional':dist([r['notional'] for r in fs]),'final_paired_qty':dist([m['final_pre_expiry']['paired_qty'] for m in ms if m['final_pre_expiry']]),'final_pair_cost_gross':dist([b['average_pair_cost'] for b in last]),'final_pair_cost_reported':dist([b['average_pair_cost_reported'] for b in last]),'max_market_imbalance_shares':dist([m['max_abs_imbalance_shares'] for m in ms]),'final_abs_normalized_imbalance':dist([abs(m['final_pre_expiry']['inventory_imbalance']) for m in ms if m['final_pre_expiry']]),'final_abs_imbalance_shares':dist([abs(m['final_pre_expiry']['imbalance_shares']) for m in ms if m['final_pre_expiry']]),'fill_timing':dict(collections.Counter('before_open' if r['timestamp']<r['market_open_timestamp'] else 'after_expiry' if r['timestamp']>r['market_open_timestamp']+seconds else ['first_third','middle_third','last_third'][min(2,int(3*(r['timestamp']-r['market_open_timestamp'])/seconds))] for r in fs)),'rebalance_eligible':sum(m['rebalance_eligible'] for m in ms),'rebalance_opposite':sum(m['rebalance_opposite'] for m in ms),'rebalance_reduces':sum(m['rebalance_reduces'] for m in ms),'same_second_mixed_batches':sum(m['same_second_mixed_batches'] for m in ms),'merges':sum(m['merges'] for m in ms),'redeems':sum(m['redeems'] for m in ms),'cash_mismatch_records':sum(abs(r['cash_minus_price_quantity'])>1e-5 for r in fs),'cash_difference_total':sum(r['cash_minus_price_quantity'] for r in fs),'thresholds':{}}
  for cut in (1.,.99,.98,.95):
   summary[str(seconds)]['thresholds'][str(cut)]={'denominator_final_paired_markets':len(last),'final_gross_pct':100*sum(b['average_pair_cost']<cut for b in last)/len(last) if last else None,'final_reported_pct':100*sum(b['average_pair_cost_reported']<cut for b in last)/len(last) if last else None,'ever_gross_markets':sum(m['min_pair_cost'] is not None and m['min_pair_cost']<cut for m in ms),'ever_reported_markets':sum(m['min_pair_cost_reported'] is not None and m['min_pair_cost_reported']<cut for m in ms),'seconds_per_ever_market':dist([m['under_threshold'][str(cut)]['seconds'] for m in ms if m['under_threshold'][str(cut)]['seconds']>0]),'total_share_seconds':sum(m['under_threshold'][str(cut)]['paired_share_seconds'] for m in ms)}
 cross=json.loads((ROOT/'raw/crosscheck_trades.body').read_text())
 def crosskey(r):return tuple(str(r.get(k,'')) for k in ('transactionHash','timestamp','conditionId','asset','side','size','price'))
 aset=set(crosskey(r) for r in unique if r['type']=='TRADE'); matched=sum(crosskey(r) in aset for r in cross)
 checks={'raw_rows':len(raw),'unique_operations':len(unique),'duplicate_candidates':len(dupes),'crosscheck_trades_rows':len(cross),'crosscheck_exact_matches':matched,'btc_missing_token_ids':sum(not r['token_id'] for r in ledgers if r['type']=='TRADE'),'btc_missing_hash':sum(not r['transaction_hash'] for r in ledgers),'btc_before_redeem_invalid_inventory':sum(r['inventory_status'] in ('sell_exceeds_observed_inventory','merge_exceeds_observed_inventory','split_cost_allocation_unknown') for r in ledgers),'time_order_nondecreasing':all(a['timestamp']<=b['timestamp'] for rs in groups.values() for a,b in zip(rs,rs[1:])),'analysis_start':iso(START),'analysis_end_exclusive':iso(END)}
 dump('statistics.json',summary);dump('validation.json',checks)
 # Choose complete, reasonably short examples and counterexamples using predeclared contrasting cases.
 eligible=[m for m in markets if 6<=m['fills']<=45 and m['both_outcomes_bought'] and m['final_pre_expiry'] and m['final_pre_expiry']['average_pair_cost'] is not None]
 selected=[]
 selectors=[('pair_cost_below_095',lambda m:m['final_pre_expiry']['average_pair_cost']<.95,lambda m:m['final_pre_expiry']['average_pair_cost']),('pair_cost_above_1',lambda m:m['final_pre_expiry']['average_pair_cost']>1,lambda m:-m['final_pre_expiry']['average_pair_cost']),('frequent_alternation',lambda m:True,lambda m:-(m['up_to_down']+m['down_to_up'])),('merge',lambda m:m['merges']>0,lambda m:m['fills'])]
 for label,pred,sort in selectors:
  candidates=sorted([m for m in eligible if pred(m) and m['condition_id'] not in {s['condition_id'] for s in selected}],key=sort)
  if candidates:selected.append({'selection_reason':label,**candidates[0]})
 dump('examples_selected.json',selected)
 print(json.dumps({'validation':checks,'summary':{k:{x:v[x] for x in ['markets','fills','both_outcomes_pct','types','final_pair_cost_gross','final_pair_cost_reported']} for k,v in summary.items()}},indent=2))
if __name__=='__main__':main()

