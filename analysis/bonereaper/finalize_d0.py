import json, sqlite3, statistics
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SNAP=ROOT/'analysis_bonereaper_snapshot.db'; OUT=ROOT/'analysis'/'bonereaper'
conn=sqlite3.connect(f'file:{SNAP}?mode=ro',uri=True)
q=lambda s,a=(): conn.execute(s,a).fetchone()
fills,first,last=q("select count(*),min(timestamp),max(timestamp) from benchmark_activity where benchmark='Bonereaper'")
markets=q("select count(distinct condition_id) from benchmark_activity where benchmark='Bonereaper'")[0]
first_row=q("select timestamp,price,size,usdc_size,outcome,side,condition_id from benchmark_activity where benchmark='Bonereaper' order by timestamp,id limit 1")
last_row=q("select timestamp,price,size,usdc_size,outcome,side,condition_id from benchmark_activity where benchmark='Bonereaper' order by timestamp desc,id desc limit 1")
notional_avg,notional_total,notional_max=q("select avg(usdc_size),sum(usdc_size),max(usdc_size) from benchmark_activity where benchmark='Bonereaper'")
side=conn.execute("select side,count(*) from benchmark_activity where benchmark='Bonereaper' group by side").fetchall()
outcome=conn.execute("select outcome,count(*) from benchmark_activity where benchmark='Bonereaper' group by outcome").fetchall()
conn.close()
def iso(ts): return datetime.fromtimestamp(ts,timezone.utc).isoformat()
cap=json.load(open(OUT/'capital_analysis.json'))
cap['first_trade']={'timestamp':first_row[0],'utc':iso(first_row[0]),'price':first_row[1],'size':first_row[2],'notional':first_row[3],'outcome':first_row[4],'side':first_row[5],'market':first_row[6]}
cap['snapshot_first_30d_notional']=cap.pop('first_30d',None)
cap['capital_minimum_observable']=cap['snapshot_first_30d_notional']
json.dump(cap,open(OUT/'capital_analysis.json','w'),indent=2)
seq=json.load(open(OUT/'sequence_analysis.json')); sizing=json.load(open(OUT/'sizing_analysis.json')); pair=json.load(open(OUT/'pairing_analysis.json'))
top=[
 {'finding':'Dataset size','value':fills,'status':'SOLID'},
 {'finding':'Markets observed','value':markets,'status':'SOLID'},
 {'finding':'Period','value':f'{iso(first)} -> {iso(last)}','status':'SOLID'},
 {'finding':'BUY share','value':side[0][1]/fills if side[0][0]=='BUY' else side[1][1]/fills,'status':'SOLID'},
 {'finding':'UP share','value':next(n/fills for o,n in outcome if o=='Up'),'status':'SOLID'},
 {'finding':'P(next=DOWN|UP)','value':seq['p_next_down_given_up'],'status':'SOLID descriptive'},
 {'finding':'P(next=UP|DOWN)','value':seq['p_next_up_given_down'],'status':'SOLID descriptive'},
 {'finding':'Median fill size','value':sizing['median'],'status':'SOLID'},
 {'finding':'Average fill notional USDC','value':notional_avg,'status':'SOLID'},
 {'finding':'Markets with both outcomes average cost','value':pair['markets_with_both_outcomes'],'status':'DESCRIPTIVE, not proof of pairing'},
]
json.dump(top,open(OUT/'top_10_discoveries.json','w'),indent=2)
report=f'''# BONEREAPER - PRELIMINARY REVERSE ENGINEERING

## Dataset
- Snapshot: `{SNAP.name}` ({SNAP.stat().st_size:,} bytes)
- Period: {iso(first)} to {iso(last)} ({(last-first)/86400:.2f} days)
- Fills: {fills:,}
- Markets: {markets:,}
- Snapshot is discovery/train data only; later imports remain validation/OOS.

## Top 10 quantitative discoveries
1. {fills:,} fills across {markets:,} markets. **Solid.**
2. Coverage spans {iso(first)} to {iso(last)}. **Solid.**
3. BUY/SELL counts: {dict(side)}. **Solid.**
4. Outcome counts: {dict(outcome)}. **Solid.**
5. P(next=DOWN | previous=UP) = {seq['p_next_down_given_up']:.4f}. **Solid descriptive, not predictive.**
6. P(next=UP | previous=DOWN) = {seq['p_next_up_given_down']:.4f}. **Solid descriptive, not predictive.**
7. Median fill size = {sizing['median']}; P99 = {sizing['p99']}; max = {sizing['max']}. **Solid.**
8. Mean fill notional = {notional_avg:.4f} USDC; total observed notional = {notional_total:.2f} USDC. **Solid observed flow, not capital.**
9. {pair['markets_with_both_outcomes']:,} markets have both outcome average-cost fields. **Descriptive only; not proof of economic pairing.**
10. Largest observed fill notional = {notional_max:.2f} USDC. **Solid observation.**

## Data quality
All missing-field and invalid-timestamp counters are zero in `data_quality.json`; duplicate key groups are zero in the snapshot.

## Inventory / temporal pairing
Signed inventory and accounting exposure are reconstructed per condition/outcome. Pair-cost fields are descriptive where both sides exist. No settlement-aware pairing, hedge rate, or arbitrage claim is made. A first leg alone is not treated as an arbitrage.

## Sizing / timing / price
The median size is {sizing['median']}, with mean {sizing['mean']:.4f}; rounded recurring blocks are recorded in `sizing_analysis.json`. Market open/expiry fields are absent from the activity rows, so time-from-open and late-window analysis are not testable in D0. Price buckets are in `sizing_analysis.json`.

## Capital minimum observable
Cumulative first-30-day observed trade notional: {cap['capital_minimum_observable']:.2f} USDC. This is **not** initial capital or wallet balance; deposits, withdrawals, inventory transfers, settlement and rebates are unavailable.

## Hypotheses
- H1 Temporal pairing: **IMPOSSIBLE TO CONFIRM** with settlement-unaware activity.
- H2 Inventory management: **DESCRIPTIVE ONLY**; inventory imbalance is measurable, intent is not.
- H3 Directional momentum: **IMPOSSIBLE TO TEST** without settlement/outcome evaluation.
- H4 Late window: **IMPOSSIBLE TO TEST** without reliable market open/expiry metadata.
- H5 Cross-market: **NOT TESTED in D0**.
- H6 SPRT/sequential evidence: **NOT TESTED in D0**.

## Limitations
Public activity can omit fills and does not provide complete settlement, wallet capital, rebates, or market lifecycle metadata. Snapshot is a discovery/train dataset. No live strategy, order, or Phase A/B/C code was changed.
'''
(OUT/'report.md').write_text(report,encoding='utf-8')
print('finalized',OUT)
