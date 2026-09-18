import json
import math
import os
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'analysis_bonereaper_snapshot.db'
OUT = ROOT / 'analysis' / 'bonereaper'
OUT.mkdir(parents=True, exist_ok=True)


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def q(conn, sql, args=()):
    return conn.execute(sql, args).fetchone()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding='utf-8')


def main():
    if not SNAPSHOT.exists():
        raise SystemExit(f'Missing snapshot: {SNAPSHOT}')
    conn = sqlite3.connect(f'file:{SNAPSHOT}?mode=ro', uri=True)
    where = "benchmark='Bonereaper'"
    total, first, last = q(conn, f'SELECT count(*), min(timestamp), max(timestamp) FROM benchmark_activity WHERE {where}')
    markets = q(conn, f'SELECT count(DISTINCT condition_id) FROM benchmark_activity WHERE {where}')[0]
    quality = {
        'fills': total,
        'duplicate_key_groups': q(conn, f'''SELECT count(*) FROM (SELECT benchmark,transaction_hash,timestamp,asset,side,size,price,count(*) n FROM benchmark_activity WHERE {where} GROUP BY 1,2,3,4,5,6,7 HAVING n>1)''')[0],
        'invalid_timestamps': q(conn, f'SELECT count(*) FROM benchmark_activity WHERE {where} AND (timestamp IS NULL OR timestamp<=0)')[0],
        'missing_price': q(conn, f'SELECT count(*) FROM benchmark_activity WHERE {where} AND price IS NULL')[0],
        'missing_size': q(conn, f'SELECT count(*) FROM benchmark_activity WHERE {where} AND size IS NULL')[0],
        'missing_outcome': q(conn, f'SELECT count(*) FROM benchmark_activity WHERE {where} AND (outcome IS NULL OR outcome="")')[0],
        'missing_market': q(conn, f'SELECT count(*) FROM benchmark_activity WHERE {where} AND (condition_id IS NULL OR condition_id="")')[0],
        'missing_side': q(conn, f'SELECT count(*) FROM benchmark_activity WHERE {where} AND (side IS NULL OR side="")')[0],
    }
    write('data_quality.json', {'snapshot': str(SNAPSHOT), 'period': {'first': utc(first), 'last': utc(last)}, **quality})

    by_market = {}
    global_sizes = []
    price_bins = Counter(); outcome_counts = Counter(); side_counts = Counter(); transitions = Counter(); delay_bins = Counter(); pair_cost_bins = Counter()
    sequence_counts = Counter(); daily = defaultdict(lambda: {'fills': 0, 'volume': 0.0, 'notional': 0.0})
    size_blocks = Counter(); market_features = []
    capital = {'first_trade': None, 'first_24h_fills': 0, 'first_24h_notional': 0.0, 'first_7d_notional': 0.0, 'first_30d_notional': 0.0}
    start_ts = first or 0
    inventory = defaultdict(lambda: {'UP': 0.0, 'DOWN': 0.0, 'cost_up': 0.0, 'cost_down': 0.0, 'last': None, 'switches': 0, 'delays': [], 'fills': 0, 'pair_costs': []})
    previous = {}
    rows = conn.execute(f'''SELECT timestamp,condition_id,side,outcome,price,size,usdc_size,title,slug FROM benchmark_activity WHERE {where} ORDER BY condition_id,timestamp,id''')
    for ts, market, side, outcome, price, size, usdc, title, slug in rows:
        outcome = (outcome or '').upper(); side = (side or '').upper(); price = float(price or 0); size = float(size or 0); usdc = float(usdc or price * size)
        global_sizes.append(size); outcome_counts[outcome] += 1; side_counts[side] += 1
        daily[datetime.fromtimestamp(ts, timezone.utc).date().isoformat()]['fills'] += 1
        daily[datetime.fromtimestamp(ts, timezone.utc).date().isoformat()]['volume'] += size
        daily[datetime.fromtimestamp(ts, timezone.utc).date().isoformat()]['notional'] += usdc
        capital['first_24h_fills'] += ts < start_ts + 86400
        capital['first_24h_notional'] += usdc if ts < start_ts + 86400 else 0
        capital['first_7d_notional'] += usdc if ts < start_ts + 7*86400 else 0
        capital['first_30d_notional'] += usdc if ts < start_ts + 30*86400 else 0
        if capital['first_trade'] is None: capital['first_trade'] = {'timestamp': ts, 'utc': utc(ts), 'price': price, 'size': size, 'notional': usdc, 'outcome': outcome, 'side': side, 'market': market}
        if 0 <= price <= 1:
            if price < .1: b='0-10c'
            elif price < .2: b='10-20c'
            elif price < .3: b='20-30c'
            elif price < .4: b='30-40c'
            elif price < .5: b='40-50c'
            elif price < .6: b='50-60c'
            elif price < .7: b='60-70c'
            elif price < .8: b='70-80c'
            elif price < .9: b='80-90c'
            elif price < .95: b='90-95c'
            elif price < .98: b='95-98c'
            elif price < .99: b='98-99c'
            else: b='99-100c'
            price_bins[b] += 1
        key = (market, outcome)
        inv = inventory[market]
        if outcome in ('UP','DOWN'):
            sign = 1 if side == 'BUY' else -1
            inv[outcome] += sign * size
            inv['cost_up' if outcome == 'UP' else 'cost_down'] += sign * size * price
        inv['fills'] += 1
        prev = previous.get(market)
        if prev:
            transitions[(prev[0], outcome)] += 1
            if prev[0] != outcome:
                delay = max(0, ts - prev[1])
                inv['delays'].append(delay)
                delay_bins['<100ms' if delay < .1 else '100-500ms' if delay < .5 else '500ms-1s' if delay < 1 else '1-5s' if delay < 5 else '5-15s' if delay < 15 else '15-30s' if delay < 30 else '30-60s' if delay < 60 else '>60s'] += 1
                inv['switches'] += 1
        previous[market] = (outcome, ts)
        size_blocks[round(size, -1)] += 1
    conn.close()

    for market, inv in inventory.items():
        up=max(inv['UP'],0); down=max(inv['DOWN'],0); paired=min(up,down); imbalance=up-down
        avg_up=inv['cost_up']/inv['UP'] if inv['UP'] else None; avg_down=inv['cost_down']/inv['DOWN'] if inv['DOWN'] else None
        feature={'market':market,'fills':inv['fills'],'inventory_up':up,'inventory_down':down,'paired_inventory':paired,'directional_up':max(imbalance,0),'directional_down':max(-imbalance,0),'inventory_imbalance':imbalance,'average_up_price':avg_up,'average_down_price':avg_down,'side_switch_count':inv['switches'],'median_switch_delay':statistics.median(inv['delays']) if inv['delays'] else None}
        market_features.append(feature)
        if avg_up is not None and avg_down is not None: pair_cost_bins['<0.85' if avg_up+avg_down<.85 else '0.85-0.90' if avg_up+avg_down<.90 else '0.90-0.93' if avg_up+avg_down<.93 else '0.93-0.95' if avg_up+avg_down<.95 else '0.95-0.97' if avg_up+avg_down<.97 else '0.97-0.99' if avg_up+avg_down<.99 else '0.99-1.00' if avg_up+avg_down<=1 else '>1.00'] += 1
    trans_total=sum(transitions.values())
    sequence={'transitions':dict({f'{a}->{b}':n for (a,b),n in transitions.items()}),'p_next_down_given_up': transitions[('UP','DOWN')]/max(transitions[('UP','UP')]+transitions[('UP','DOWN')],1),'p_next_up_given_down': transitions[('DOWN','UP')]/max(transitions[('DOWN','UP')]+transitions[('DOWN','DOWN')],1),'delay_distribution':dict(delay_bins),'transition_total':trans_total}
    sizing={'count':len(global_sizes),'mean':statistics.mean(global_sizes) if global_sizes else None,'median':statistics.median(global_sizes) if global_sizes else None,'p25':statistics.quantiles(global_sizes,n=4)[0] if len(global_sizes)>1 else None,'p75':statistics.quantiles(global_sizes,n=4)[2] if len(global_sizes)>1 else None,'p90':statistics.quantiles(global_sizes,n=10)[8] if len(global_sizes)>1 else None,'p95':statistics.quantiles(global_sizes,n=20)[18] if len(global_sizes)>1 else None,'p99':statistics.quantiles(global_sizes,n=100)[98] if len(global_sizes)>1 else None,'max':max(global_sizes) if global_sizes else None,'common_rounded_sizes':size_blocks.most_common(20),'price_bins':dict(price_bins)}
    write('reconstruction_summary.json',{'fills':total,'markets':markets,'period':{'first':utc(first),'last':utc(last)},'market_features':market_features[:5000]})
    write('sequence_analysis.json',sequence); write('pairing_analysis.json',{'pair_cost_distribution':dict(pair_cost_bins),'note':'Average inventory cost pairing is descriptive; no economic pairing inferred across unresolved sells.','markets_with_both_outcomes':sum(1 for x in market_features if x['average_up_price'] is not None and x['average_down_price'] is not None)})
    write('sizing_analysis.json',sizing); write('timing_analysis.json',{'entry_timing':'Not testable: market open/expiry timestamps are not reliably present in activity rows.','delay_distribution':dict(delay_bins)})
    write('regime_analysis.json',{'method':'Descriptive daily aggregates; no arbitrary clustering selected.','daily':daily,'market_feature_count':len(market_features)})
    write('capital_analysis.json',{'capital_minimum_observable':capital['first_30d_notional'],'definition':'Cumulative observed trade notional, not wallet starting capital.','first_trade':capital['first_trade'],'first_24h':capital['first_24h_notional'],'first_7d':capital['first_7d_notional'],'first_30d':capital['first_30d_notional']})
    write('hypothesis_validation.json',{'H1_temporal_pairing':'IMPOSSIBLE_TO_CONFIRM','H2_inventory_management':'DESCRIPTIVE_ONLY','H3_directional_momentum':'IMPOSSIBLE_TO_TEST_WITHOUT_SETTLEMENT','H4_late_window':'IMPOSSIBLE_TO_TEST_WITHOUT_MARKET_OPEN_EXPIRY','H5_cross_market':'NOT_TESTED_D0','H6_sprt':'NOT_TESTED_D0'})
    report=f'''# BONEREAPER - PRELIMINARY REVERSE ENGINEERING\n\n## Dataset\n- Snapshot: `{SNAPSHOT.name}`\n- Period: {utc(first)} to {utc(last)}\n- Fills: {total:,}\n- Markets: {markets:,}\n\n## Top observed patterns\n- Transition probabilities and delay buckets are in `sequence_analysis.json`; they are descriptive, not strategy validation.\n- Inventory was reconstructed per condition/outcome using signed BUY/SELL quantities.\n- Pairing is not treated as arbitrage without settlement evidence.\n- PnL is intentionally not calculated: settlement/resolution and complete capital flows are absent.\n\n## Temporal pairing / inventory / sizing / timing\n- Pair-cost observations are reported only when both outcome average costs exist.\n- Capital minimum observable is cumulative first-30-day trade notional, not initial capital.\n- Market open/expiry timing is unavailable from these rows.\n- Full metrics are stored in the JSON artifacts beside this report.\n\n## Hypothesis status\nH1/H3/H4 remain impossible or descriptive with this dataset; H5/H6 were not tested in D0. No live strategy was coded.\n\n## Limitations\n- Snapshot is discovery/train data only.\n- Public activity may omit fills, settlement, deposits, withdrawals, rebates, and complete market lifecycle metadata.\n- Inventory pairing is accounting exposure, not proof of economic pairing.\n'''
    (OUT/'report.md').write_text(report,encoding='utf-8')

if __name__ == '__main__': main()
