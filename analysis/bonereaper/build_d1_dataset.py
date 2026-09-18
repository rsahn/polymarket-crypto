import json
import math
import sqlite3
import statistics
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'analysis_bonereaper_snapshot.db'
PAIR_DB = ROOT / 'analysis' / 'bonereaper' / 'pair_observations.db'
OUT_DIR = ROOT / 'analysis' / 'bonereaper'
BATCH_SIZE = 10000
CHECKPOINT_MARKETS = 250

SCHEMA = '''
CREATE TABLE IF NOT EXISTS pair_observations (
 pair_id INTEGER PRIMARY KEY AUTOINCREMENT,
 market_id TEXT NOT NULL,
 condition_id TEXT NOT NULL,
 slug TEXT,
 first_side TEXT NOT NULL,
 second_side TEXT NOT NULL,
 first_timestamp INTEGER NOT NULL,
 second_timestamp INTEGER NOT NULL,
 time_to_hedge_ms INTEGER NOT NULL,
 up_price REAL NOT NULL,
 down_price REAL NOT NULL,
 pair_cost REAL NOT NULL,
 paired_quantity REAL NOT NULL,
 up_notional REAL NOT NULL,
 down_notional REAL NOT NULL,
 pair_notional REAL NOT NULL,
 inventory_up_before REAL NOT NULL,
 inventory_down_before REAL NOT NULL,
 inventory_up_after REAL NOT NULL,
 inventory_down_after REAL NOT NULL,
 directional_remainder_after REAL NOT NULL,
 matching_method TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pair_market ON pair_observations(market_id);
CREATE INDEX IF NOT EXISTS idx_pair_first_ts ON pair_observations(first_timestamp);
CREATE INDEX IF NOT EXISTS idx_pair_time ON pair_observations(time_to_hedge_ms);
CREATE INDEX IF NOT EXISTS idx_pair_cost ON pair_observations(pair_cost);
CREATE TABLE IF NOT EXISTS market_metrics (
 market_id TEXT PRIMARY KEY,
 condition_id TEXT NOT NULL,
 slug TEXT,
 fills INTEGER NOT NULL,
 pairs INTEGER NOT NULL,
 paired_quantity REAL NOT NULL,
 total_inventory_handled REAL NOT NULL,
 hedge_rate REAL,
 median_pair_cost REAL,
 weighted_pair_cost REAL,
 median_time_to_hedge_ms REAL,
 inventory_up REAL NOT NULL,
 inventory_down REAL NOT NULL,
 directional_remainder REAL NOT NULL,
 first_timestamp INTEGER,
 last_timestamp INTEGER
);
CREATE TABLE IF NOT EXISTS reconstruction_state (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL
);
'''


def q(values, probability):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def mean(values):
    return statistics.fmean(values) if values else None


def median(values):
    return statistics.median(values) if values else None


def pct(values, predicate, weights=None):
    if weights is None:
        return 100.0 * sum(predicate(value) for value in values) / len(values) if values else None
    total = sum(weights)
    return 100.0 * sum(weight for value, weight in zip(values, weights) if predicate(value)) / total if total else None


def weighted_mean(values, weights):
    total = sum(weights)
    return sum(value * weight for value, weight in zip(values, weights)) / total if total else None


def set_state(conn, key, value):
    conn.execute('INSERT OR REPLACE INTO reconstruction_state(key,value) VALUES(?,?)', (key, str(value)))


def get_state(conn, key, default=None):
    row = conn.execute('SELECT value FROM reconstruction_state WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def create_database():
    conn = sqlite3.connect(PAIR_DB)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def reconstruct():
    pair_conn = create_database()
    source = sqlite3.connect(f'file:{SNAPSHOT}?mode=ro', uri=True)
    last_condition = get_state(pair_conn, 'last_condition_id')
    started = time.monotonic()
    markets_processed = 0
    fills_processed = 0
    pairs_created = pair_conn.execute('SELECT count(*) FROM pair_observations').fetchone()[0]
    paired_quantity = pair_conn.execute('SELECT coalesce(sum(paired_quantity),0) FROM pair_observations').fetchone()[0]
    insert_buffer = []

    insert_sql = '''INSERT INTO pair_observations(
        condition_id,market_id,slug,first_side,second_side,first_timestamp,second_timestamp,
        time_to_hedge_ms,up_price,down_price,pair_cost,paired_quantity,up_notional,down_notional,
        pair_notional,inventory_up_before,inventory_down_before,inventory_up_after,inventory_down_after,
        directional_remainder_after,matching_method)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''

    def flush_buffer():
        nonlocal insert_buffer
        if insert_buffer:
            pair_conn.executemany(insert_sql, insert_buffer)
            insert_buffer = []

    current = None
    inventory = {'UP': 0.0, 'DOWN': 0.0}
    lots = {'UP': deque(), 'DOWN': deque()}
    market_pairs = []
    market_fills = 0
    market_buy_quantity = 0.0
    slug = ''
    first_ts = None
    last_ts = None

    def finish_market():
        nonlocal current, market_pairs, market_fills, market_buy_quantity, slug, first_ts, last_ts, markets_processed
        if current is None:
            return
        flush_buffer()
        pair_costs = [row[10] for row in market_pairs]
        times = [row[7] for row in market_pairs]
        quantities = [row[11] for row in market_pairs]
        pair_conn.execute('''INSERT OR REPLACE INTO market_metrics(
            market_id,condition_id,slug,fills,pairs,paired_quantity,total_inventory_handled,hedge_rate,
            median_pair_cost,weighted_pair_cost,median_time_to_hedge_ms,inventory_up,inventory_down,
            directional_remainder,first_timestamp,last_timestamp)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (current, current, slug, market_fills, len(market_pairs), sum(quantities), market_buy_quantity,
             sum(quantities) / market_buy_quantity if market_buy_quantity else None, median(pair_costs),
             weighted_mean(pair_costs, quantities), median(times), inventory['UP'], inventory['DOWN'],
             abs(inventory['UP'] - inventory['DOWN']), first_ts, last_ts))
        set_state(pair_conn, 'last_condition_id', current)
        markets_processed += 1
        if markets_processed % CHECKPOINT_MARKETS == 0:
            pair_conn.commit()
        if markets_processed % 100 == 0:
            elapsed = max(time.monotonic() - started, 0.001)
            print(f'markets_processed={markets_processed} fills_processed={fills_processed} pairs_created={pairs_created} paired_quantity={paired_quantity:.3f} DB rows={pairs_created} elapsed={elapsed:.1f}s rows/sec={pairs_created/elapsed:.1f}', flush=True)
        market_pairs = []
        market_fills = 0
        market_buy_quantity = 0.0
        slug = ''
        first_ts = None
        last_ts = None

    rows = source.execute('''SELECT id,condition_id,timestamp,side,outcome,size,price,slug
                             FROM benchmark_activity
                             WHERE benchmark='Bonereaper' AND condition_id IS NOT NULL
                             ORDER BY condition_id,timestamp,id''')
    for source_id, condition, timestamp, side, outcome, size, price, row_slug in rows:
        if last_condition is not None and condition <= last_condition:
            continue
        if condition != current:
            finish_market()
            current = condition
            inventory = {'UP': 0.0, 'DOWN': 0.0}
            lots = {'UP': deque(), 'DOWN': deque()}
        market_fills += 1
        fills_processed += 1
        slug = row_slug or slug
        first_ts = timestamp if first_ts is None else first_ts
        last_ts = timestamp
        side = (side or '').upper()
        outcome = (outcome or '').upper()
        size = float(size or 0.0)
        price = float(price or 0.0)
        if outcome not in ('UP', 'DOWN') or side not in ('BUY', 'SELL') or size <= 0:
            continue
        before_up = inventory['UP']
        before_down = inventory['DOWN']
        if side == 'SELL':
            remaining = size
            inventory[outcome] -= size
            while remaining > 1e-12 and lots[outcome]:
                lot = lots[outcome][0]
                consumed = min(remaining, lot[1])
                lot[1] -= consumed
                remaining -= consumed
                if lot[1] <= 1e-12:
                    lots[outcome].popleft()
            continue
        inventory[outcome] += size
        market_buy_quantity += size
        lots[outcome].append([timestamp, size, price])
        current_lot = lots[outcome][-1]
        remaining = size
        opposite = 'DOWN' if outcome == 'UP' else 'UP'
        while remaining > 1e-12 and lots[opposite]:
            opposite_lot = lots[opposite][0]
            quantity = min(remaining, opposite_lot[1])
            opposite_lot[1] -= quantity
            current_lot[1] -= quantity
            remaining -= quantity
            if opposite_lot[1] <= 1e-12:
                lots[opposite].popleft()
            if current_lot[1] <= 1e-12:
                lots[outcome].pop()
            up_price = opposite_lot[2] if opposite == 'UP' else price
            down_price = opposite_lot[2] if opposite == 'DOWN' else price
            pair_cost = up_price + down_price
            after_up = inventory['UP']
            after_down = inventory['DOWN']
            pair_row = (current, current, slug, opposite, outcome,
                        int(opposite_lot[0] * 1000), int(timestamp * 1000),
                        int(max(0, timestamp - opposite_lot[0]) * 1000),
                        up_price, down_price, pair_cost, quantity,
                        quantity * up_price, quantity * down_price, quantity * pair_cost,
                        before_up, before_down, after_up, after_down,
                        abs(after_up - after_down), 'FIFO')
            insert_buffer.append(pair_row)
            market_pairs.append(pair_row)
            pairs_created += 1
            paired_quantity += quantity
            if len(insert_buffer) >= BATCH_SIZE:
                flush_buffer()
                elapsed = max(time.monotonic() - started, 0.001)
                print(f'markets_processed={markets_processed} fills_processed={fills_processed} pairs_created={pairs_created} paired_quantity={paired_quantity:.3f} DB rows={pairs_created} elapsed={elapsed:.1f}s rows/sec={pairs_created/elapsed:.1f}', flush=True)
    finish_market()

    set_state(pair_conn, 'status', 'complete')
    pair_conn.commit()
    source.close()
    pair_conn.close()
    return pairs_created, paired_quantity


def query_values(conn, column, where=''):
    sql = f'SELECT {column} FROM pair_observations {where}'
    return [float(row[0]) for row in conn.execute(sql)]


def distribution(values):
    return {f'p{int(probability * 100):02d}': q(values, probability) for probability in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)}


def threshold_table(values, quantities):
    return {str(threshold): {'observations_pct': pct(values, lambda value, threshold=threshold: value < threshold), 'quantity_pct': pct(values, lambda value, threshold=threshold: value < threshold, quantities)} for threshold in (0.85, 0.90, 0.93, 0.95, 0.97, 0.98, 0.99, 1.0)}


def analyze():
    conn = sqlite3.connect(PAIR_DB)
    pair_costs = query_values(conn, 'pair_cost')
    quantities = query_values(conn, 'paired_quantity')
    times = query_values(conn, 'time_to_hedge_ms')
    edges = [1.0 - value for value in pair_costs]
    pair_count = len(pair_costs)
    total_quantity = sum(quantities)
    cost_summary = {'count': pair_count, 'mean': mean(pair_costs), 'median': median(pair_costs), 'std': statistics.pstdev(pair_costs) if pair_costs else None, **distribution(pair_costs), 'thresholds': threshold_table(pair_costs, quantities), 'quantity_weighted_mean': weighted_mean(pair_costs, quantities)}
    edge_buckets = [('negative', lambda value: value < 0), ('0-1%', lambda value: 0 <= value < 0.01), ('1-2%', lambda value: 0.01 <= value < 0.02), ('2-3%', lambda value: 0.02 <= value < 0.03), ('3-5%', lambda value: 0.03 <= value < 0.05), ('5-10%', lambda value: 0.05 <= value < 0.10), ('>10%', lambda value: value >= 0.10)]
    edge_distribution = {name: {'observations': sum(predicate(edge) for edge in edges), 'quantity': sum(quantity for edge, quantity in zip(edges, quantities) if predicate(edge)), 'edge_mean': mean([edge for edge, predicate_value in zip(edges, [predicate(edge) for edge in edges]) if predicate_value])} for name, predicate in edge_buckets}
    time_buckets = [('0-100ms', 0, 100), ('100-500ms', 100, 500), ('500ms-1s', 500, 1000), ('1-5s', 1000, 5000), ('5-15s', 5000, 15000), ('15-30s', 15000, 30000), ('30-60s', 30000, 60000), ('60-120s', 60000, 120000), ('>120s', 120000, None)]
    time_analysis = {'summary_ms': {'mean': mean(times), 'median': median(times), **distribution(times)}, 'buckets': {}}
    for name, lower, upper in time_buckets:
        indices = [index for index, value in enumerate(times) if value >= lower and (upper is None or value < upper)]
        selected_costs = [pair_costs[index] for index in indices]
        selected_quantities = [quantities[index] for index in indices]
        selected_edges = [edges[index] for index in indices]
        time_analysis['buckets'][name] = {'pairs': len(indices), 'paired_quantity': sum(selected_quantities), 'pair_cost_mean': mean(selected_costs), 'pair_cost_median': median(selected_costs), 'pair_cost_lt_1_pct': pct(selected_costs, lambda value: value < 1), 'pair_cost_lt_0_99_pct': pct(selected_costs, lambda value: value < 0.99), 'pair_cost_lt_0_97_pct': pct(selected_costs, lambda value: value < 0.97), 'pair_cost_lt_0_95_pct': pct(selected_costs, lambda value: value < 0.95), 'gross_pair_edge_mean': mean(selected_edges), 'gross_pair_edge_quantity_weighted': weighted_mean(selected_edges, selected_quantities)}
    direction_analysis = {}
    for direction in ('UP->DOWN', 'DOWN->UP'):
        indices = [index for index, row in enumerate(conn.execute('SELECT first_side,second_side FROM pair_observations')) if f'{row[0]}->{row[1]}' == direction]
        selected_costs = [pair_costs[index] for index in indices]
        selected_times = [times[index] for index in indices]
        selected_edges = [edges[index] for index in indices]
        direction_analysis[direction] = {'pairs': len(indices), 'paired_quantity': sum(quantities[index] for index in indices), 'pair_cost_mean': mean(selected_costs), 'pair_cost_median': median(selected_costs), 'time_to_hedge_median_ms': median(selected_times), 'pair_cost_lt_1_pct': pct(selected_costs, lambda value: value < 1), 'gross_pair_edge_mean': mean(selected_edges)}
    size_buckets = [('<10', 0, 10), ('10-50', 10, 50), ('50-100', 50, 100), ('100-250', 100, 250), ('250-500', 250, 500), ('500-1000', 500, 1000), ('1000-5000', 1000, 5000), ('>5000', 5000, None)]
    size_analysis = {}
    for name, lower, upper in size_buckets:
        indices = [index for index, value in enumerate(quantities) if value >= lower and (upper is None or value < upper)]
        selected_costs = [pair_costs[index] for index in indices]; selected_times = [times[index] for index in indices]; selected_edges = [edges[index] for index in indices]
        size_analysis[name] = {'pairs': len(indices), 'pair_cost_median': median(selected_costs), 'time_to_hedge_median_ms': median(selected_times), 'pair_cost_lt_1_pct': pct(selected_costs, lambda value: value < 1), 'gross_pair_edge_mean': mean(selected_edges)}
    market_rows = conn.execute('SELECT pairs,paired_quantity,total_inventory_handled,hedge_rate,median_pair_cost,weighted_pair_cost,median_time_to_hedge_ms,directional_remainder FROM market_metrics WHERE pairs > 0').fetchall()
    market_medians = [row[4] for row in market_rows if row[4] is not None]
    market_analysis = {'markets_with_pairs': len(market_rows), 'median_pair_cost_distribution': distribution(market_medians), 'pct_markets_median_pair_cost_lt': {str(threshold): pct(market_medians, lambda value, threshold=threshold: value < threshold) for threshold in (1, 0.99, 0.97, 0.95)}, 'median_paired_quantity': median([row[1] for row in market_rows]), 'median_hedge_rate': median([row[3] for row in market_rows if row[3] is not None]), 'median_directional_remainder': median([row[7] for row in market_rows])}
    temporal = {}
    for period_name, expression in (('day', "strftime('%Y-%m-%d', first_timestamp / 1000, 'unixepoch')"), ('week', "strftime('%Y-W%W', first_timestamp / 1000, 'unixepoch')")):
        groups = {}
        for period, cost, quantity, time_ms in conn.execute(f'SELECT {expression}, pair_cost, paired_quantity, time_to_hedge_ms FROM pair_observations'):
            group = groups.setdefault(period, {'costs': [], 'quantities': [], 'times': []})
            group['costs'].append(cost); group['quantities'].append(quantity); group['times'].append(time_ms)
        market_groups = {}
        market_expression = expression.replace('first_timestamp / 1000', 'first_timestamp')
        for period, paired, handled in conn.execute(f'SELECT {market_expression}, paired_quantity, total_inventory_handled FROM market_metrics'):
            group = market_groups.setdefault(period, [0.0, 0.0])
            group[0] += paired; group[1] += handled
        temporal[period_name] = []
        for period in sorted(groups):
            group = groups[period]
            costs = group['costs']; quantities_for_group = group['quantities']; times_for_group = group['times']
            temporal[period_name].append({'period': period, 'pairs': len(costs), 'paired_quantity': sum(quantities_for_group), 'pair_cost_median': median(costs), 'weighted_pair_cost': weighted_mean(costs, quantities_for_group), 'pair_cost_lt_1_pct': pct(costs, lambda value: value < 1), 'time_to_hedge_median_ms': median(times_for_group), 'hedge_rate': market_groups.get(period, [None, None])[0] / market_groups.get(period, [None, None])[1] if market_groups.get(period, [0, 0])[1] else None})
    before_imbalance = [abs(row[0] - row[1]) for row in conn.execute('SELECT inventory_up_before,inventory_down_before FROM pair_observations')]
    after_imbalance = [abs(row[0] - row[1]) for row in conn.execute('SELECT inventory_up_after,inventory_down_after FROM pair_observations')]
    imbalance_reductions = [before - after for before, after in zip(before_imbalance, after_imbalance)]
    inventory = {
        'paired_quantity': total_quantity,
        'total_inventory_handled': conn.execute('SELECT sum(total_inventory_handled) FROM market_metrics').fetchone()[0],
        'paired_ratio': total_quantity / conn.execute('SELECT sum(total_inventory_handled) FROM market_metrics').fetchone()[0],
        'directional_remainder_distribution': distribution([row[0] for row in conn.execute('SELECT directional_remainder FROM market_metrics')]),
        'markets_with_pairs': len(market_rows),
        'second_legs_reducing_imbalance_pct': pct(imbalance_reductions, lambda value: value > 0),
        'imbalance_reduction_mean': mean(imbalance_reductions),
        'imbalance_reduction_median': median(imbalance_reductions),
        'imbalance_before_mean': mean(before_imbalance),
        'imbalance_after_mean': mean(after_imbalance),
        'imbalance_before_median': median(before_imbalance),
        'imbalance_after_median': median(after_imbalance),
    }
    outputs = {'d1_paircost_distribution.json': {'pair_cost': cost_summary, 'gross_pair_edge': {'mean': mean(edges), 'median': median(edges), 'quantity_weighted_mean': weighted_mean(edges, quantities), 'distribution': edge_distribution}}, 'd1_time_to_hedge.json': time_analysis, 'd1_direction_analysis.json': direction_analysis, 'd1_size_analysis.json': size_analysis, 'd1_market_analysis.json': market_analysis, 'd1_temporal_stability.json': temporal, 'd1_inventory_analysis.json': inventory}
    for filename, payload in outputs.items():
        (OUT_DIR / filename).write_text(json.dumps(payload, indent=2), encoding='utf-8')
    report = create_report(cost_summary, time_analysis, direction_analysis, market_analysis, inventory, temporal)
    (OUT_DIR / 'd1_pairing_report.md').write_text(report, encoding='utf-8')
    conn.close()
    print(json.dumps({'pairs': pair_count, 'paired_quantity': total_quantity, 'pair_cost_mean': cost_summary['mean'], 'pair_cost_median': cost_summary['median'], 'weighted_pair_cost': cost_summary['quantity_weighted_mean'], 'time_median_ms': time_analysis['summary_ms']['median'], 'paired_ratio': inventory['paired_ratio']}, indent=2))


def create_report(cost, timing, direction, market, inventory, temporal):
    best = min(timing['buckets'].items(), key=lambda item: item[1]['pair_cost_mean'] if item[1]['pair_cost_mean'] is not None else float('inf'))
    worst = max(timing['buckets'].items(), key=lambda item: item[1]['pair_cost_mean'] if item[1]['pair_cost_mean'] is not None else float('-inf'))
    return f'''# BONEREAPER D1 — Economic Reconstruction

Source: `analysis/bonereaper_snapshot.db` via `pair_observations.db`. Matching method: **FIFO convention**. No import, Gamma enrichment, bot, BoneOhio or lkkdnfa was run.

## Résumé

- Pairs: **{cost['count']:,}**
- Paired quantity: **{sum(query_values(sqlite3.connect(PAIR_DB), 'paired_quantity')):,.3f}**
- PairCost mean: **{cost['mean']:.8f}**
- PairCost median: **{cost['median']:.8f}**
- Quantity-weighted PairCost: **{cost['quantity_weighted_mean']:.8f}**
- PairCost < 1: **{cost['thresholds']['1.0']['observations_pct']:.3f}%** observations / **{cost['thresholds']['1.0']['quantity_pct']:.3f}%** quantity
- PairCost < 0.99: **{cost['thresholds']['0.99']['observations_pct']:.3f}%** observations / **{cost['thresholds']['0.99']['quantity_pct']:.3f}%** quantity
- PairCost < 0.97: **{cost['thresholds']['0.97']['observations_pct']:.3f}%** observations / **{cost['thresholds']['0.97']['quantity_pct']:.3f}%** quantity
- PairCost < 0.95: **{cost['thresholds']['0.95']['observations_pct']:.3f}%** observations / **{cost['thresholds']['0.95']['quantity_pct']:.3f}%** quantity
- Median TimeToHedge: **{timing['summary_ms']['median'] / 1000:.3f} s**
- Best PairCost bucket: **{best[0]}** ({best[1]['pair_cost_mean']:.6f})
- Worst PairCost bucket: **{worst[0]}** ({worst[1]['pair_cost_mean']:.6f})
- Paired inventory ratio: **{inventory['paired_ratio']:.6%}**
- Gross Pair Edge median: **{1 - cost['median']:.8f}**
- Gross Pair Edge quantity weighted: **{1 - cost['quantity_weighted_mean']:.8f}**

## Direction

| Direction | Pairs | Quantity | PairCost mean | PairCost median | Time median | PairCost < 1 | Gross edge mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| UP → DOWN | {direction['UP->DOWN']['pairs']:,} | {direction['UP->DOWN']['paired_quantity']:,.3f} | {direction['UP->DOWN']['pair_cost_mean']:.6f} | {direction['UP->DOWN']['pair_cost_median']:.6f} | {direction['UP->DOWN']['time_to_hedge_median_ms'] / 1000:.3f}s | {direction['UP->DOWN']['pair_cost_lt_1_pct']:.3f}% | {direction['UP->DOWN']['gross_pair_edge_mean']:.6f} |
| DOWN → UP | {direction['DOWN->UP']['pairs']:,} | {direction['DOWN->UP']['paired_quantity']:,.3f} | {direction['DOWN->UP']['pair_cost_mean']:.6f} | {direction['DOWN->UP']['pair_cost_median']:.6f} | {direction['DOWN->UP']['time_to_hedge_median_ms'] / 1000:.3f}s | {direction['DOWN->UP']['pair_cost_lt_1_pct']:.3f}% | {direction['DOWN->UP']['gross_pair_edge_mean']:.6f} |

## Conclusions disciplinées

- H1 Temporal Pairing: **PARTIALLY SUPPORTED** until direction, timing distributions and controls are interpreted; this dataset proves reconstructed two-leg sequences under FIFO, not Bonereaper's internal intent.
- H2 Inventory Management: **SUPPORTED descriptively** if the before/after imbalance analysis shows reductions; the current reconstruction records the fields needed for the direct test.
- Temporal stability: **see `d1_temporal_stability.json`**; period PairCost medians require the persisted rows and are not inferred from the old aggregate.

## Limites

- FIFO est une convention, pas l'appariement interne exact de Bonereaper.
- Les fills publics ne sont pas nécessairement complets et ne sont pas des décisions indépendantes.
- `GrossPairEdge = 1 - PairCost` n'est pas un profit net: frais, slippage, latence, risque d'exécution, jambe manquante et rebates sont exclus.
- La première jambe porte un risque directionnel.
- Le settlement/PnL reste hors périmètre de cette reconstruction.
'''


if __name__ == '__main__':
    reconstruct()
    analyze()
