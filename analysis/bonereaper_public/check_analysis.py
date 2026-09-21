from pathlib import Path
import json,csv,collections,hashlib,datetime,statistics,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from analyze import dist
markets=json.loads((ROOT/'markets.json').read_text());stats=json.loads((ROOT/'statistics.json').read_text());rows=list(csv.DictReader((ROOT/'btc_inventory_ledger.csv').open(encoding='utf-8-sig')))
extras={}
for d in (300,900):
 ms=[m for m in markets if m['market_duration']==d];clean=[m for m in ms if not m['trades_after_expiry'] and m['final_pre_expiry'] and m['final_pre_expiry']['average_pair_cost'] is not None];affected=[m for m in ms if m['trades_after_expiry']]
 extras[str(d)]={'markets_with_after_expiry_trades':len(affected),'after_expiry_seconds':dist([int(r['timestamp'])-int(r['market_open_timestamp'])-d for r in rows if r['type']=='TRADE' and int(r['market_duration'])==d and int(r['timestamp'])>int(r['market_open_timestamp'])+d]),'clean_timing_paired_markets':len(clean),'clean_timing_final_pair_cost':dist([m['final_pre_expiry']['average_pair_cost'] for m in clean]),'clean_timing_final_below_1_pct':100*sum(m['final_pre_expiry']['average_pair_cost']<1 for m in clean)/len(clean) if clean else None,'clean_timing_final_reported_below_1_pct':100*sum(m['final_pre_expiry']['average_pair_cost_reported']<1 for m in clean)/len(clean) if clean else None,'multiple_fills_markets':sum(m['fills']>1 for m in ms),'threshold_max_paired_qty':{str(c):dist([m['under_threshold'][str(c)]['max_paired_qty'] for m in ms if m['under_threshold'][str(c)]['seconds']>0]) for c in (1.,.99,.98,.95)}}
# API coverage and raw hashes: no D5 filesystem paths are opened.
cov=json.loads((ROOT/'coverage.json').read_text());wins=sorted(cov['windows'],key=lambda w:w['start']);assert all(a['end']+1==b['start'] for a,b in zip(wins,wins[1:]));assert len(wins)==261
raw_errors=[];raw_total=0
for meta_path in (ROOT/'raw').glob('*.meta.json'):
 meta=json.loads(meta_path.read_text());body=meta_path.with_name(meta_path.name.replace('.meta.json','.body')).read_bytes();raw_total+=len(body)
 if hashlib.sha256(body).hexdigest()!=meta['sha256']:raw_errors.append(meta_path.name)
extras['provenance']={'contiguous_windows':True,'windows':len(wins),'start':wins[0]['start'],'end':wins[-1]['end'],'raw_bytes':raw_total,'hash_mismatches':raw_errors,'utc_checked':datetime.datetime.now(datetime.timezone.utc).isoformat()}
# Independently verify the final average gross cost for all pure BUY markets without pre-expiry settlement.
independent=0;failures=[]
by=collections.defaultdict(list)
for r in rows:by[r['condition_id']].append(r)
for m in markets:
 if not m['final_pre_expiry']:continue
 rr=[r for r in by[m['condition_id']] if int(r['timestamp'])<=m['market_open_timestamp']+m['market_duration']]
 if any(r['type']!='TRADE' or r['side']!='BUY' for r in rr):continue
 sums={s:(sum(float(r['quantity']) for r in rr if r['outcome']==s),sum(float(r['notional']) for r in rr if r['outcome']==s)) for s in ('Up','Down')}
 for s,k in [('Up','up_qty'),('Down','down_qty')]:
  if abs(sums[s][0]-m['final_pre_expiry'][k])>1e-6:failures.append(m['market_slug'])
 if all(q>0 for q,c in sums.values()):
  pc=sum(c/q for q,c in sums.values())
  if abs(pc-m['final_pre_expiry']['average_pair_cost'])>1e-9:failures.append(m['market_slug'])
 independent+=1
extras['independent_accounting']={'markets_checked':independent,'failures':failures}
(ROOT/'sensitivity_and_checks.json').write_text(json.dumps(extras,indent=2),encoding='utf-8')
print(json.dumps(extras,indent=2))
