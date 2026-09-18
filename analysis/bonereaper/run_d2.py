import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'analysis' / 'bonereaper' / 'pair_observations.db'
OUT = ROOT / 'analysis' / 'bonereaper' / 'd2'
MIN_PAIRS = 10000
MIN_MARKETS = 25
MIN_DAYS = 3
MIN_WEEKS = 2
FRICTIONS = (0.0, 0.0025, 0.005, 0.01, 0.02)
TIME_WINDOWS = {
    '1-3s': (1000, 3000), '1-5s': (1000, 5000), '3-5s': (3000, 5000),
    '5-10s': (5000, 10000), '5-15s': (5000, 15000), '10-15s': (10000, 15000),
    '15-20s': (15000, 20000), '15-30s': (15000, 30000), '20-30s': (20000, 30000),
    '30-45s': (30000, 45000), '30-60s': (30000, 60000), '45-60s': (45000, 60000),
    '60-90s': (60000, 90000), '90-120s': (90000, 120000), '>120s': (120000, None),
}
SIZE_WINDOWS = {'<10': (0, 10), '10-25': (10, 25), '25-50': (25, 50), '50-100': (50, 100), '100-250': (100, 250), '250-500': (250, 500), '500-1000': (500, 1000), '1000-2500': (1000, 2500), '2500-5000': (2500, 5000), '>5000': (5000, None)}


def q(values, p):
    if not values:
        return None
    values = sorted(values); x = (len(values) - 1) * p
    a, b = math.floor(x), math.ceil(x)
    return values[a] if a == b else values[a] + (values[b] - values[a]) * (x - a)


def sql_window(column, low, high):
    clauses = [f'{column} >= ?']; args = [low]
    if high is not None:
        clauses.append(f'{column} < ?'); args.append(high)
    return ' AND '.join(clauses), args


def metric(conn, where='1=1', args=()):
    row = conn.execute(f'''SELECT count(*), coalesce(sum(paired_quantity),0),
        avg(pair_cost), coalesce(sum(pair_cost * paired_quantity) / nullif(sum(paired_quantity),0),0),
        avg(pair_cost < 1), avg(1 - pair_cost),
        count(distinct market_id), count(distinct date(first_timestamp / 1000, 'unixepoch')),
        count(distinct strftime('%Y-W%W', first_timestamp / 1000, 'unixepoch'))
        FROM pair_observations WHERE {where}''', args).fetchone()
    return {'pairs': row[0], 'paired_quantity': row[1], 'pair_cost_mean': row[2], 'pair_cost_weighted': row[3], 'pair_cost_lt_1_pct': row[4] * 100 if row[4] is not None else None, 'gross_edge_mean': row[5], 'gross_edge_weighted': 1 - row[3] if row[3] is not None else None, 'markets': row[6], 'days': row[7], 'weeks': row[8]}


def valid(m):
    return m['pairs'] >= MIN_PAIRS and m['markets'] >= MIN_MARKETS and m['days'] >= MIN_DAYS and m['weeks'] >= MIN_WEEKS


def quantiles(conn, column, where, args):
    values = [r[0] for r in conn.execute(f'SELECT abs({column}) FROM pair_observations WHERE {where} ORDER BY abs({column})', args)]
    return {'p25': q(values, .25), 'p50': q(values, .50), 'p75': q(values, .75), 'p90': q(values, .90), 'count': len(values)}


def condition_time(low, high):
    return sql_window('time_to_hedge_ms', low, high)


def condition_size(low, high):
    return sql_window('paired_quantity', low, high)


def combine(*parts):
    clauses = []; args = []
    for clause, values in parts:
        clauses.append(f'({clause})'); args.extend(values)
    return ' AND '.join(clauses) if clauses else '1=1', args


def split_bounds(conn):
    min_ts, max_ts = conn.execute('SELECT min(first_timestamp), max(first_timestamp) FROM pair_observations').fetchone()
    span = max_ts - min_ts
    return [(min_ts, min_ts + span * .6), (min_ts + span * .6, min_ts + span * .8), (min_ts + span * .8, max_ts + 1)]


def period_clause(low, high):
    return 'first_timestamp >= ? AND first_timestamp < ?', [low, high]


def with_period(base, period):
    clause, args = base
    p_clause, p_args = period_clause(*period)
    return f'({clause}) AND ({p_clause})', args + p_args


def evaluate_rule(conn, rule, period=None):
    base = rule['where'], rule['args']
    if period is not None:
        base = with_period(base, period)
    return metric(conn, *base)


def d2():
    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    bounds = split_bounds(conn)
    train, validation, oos = bounds
    baseline = metric(conn)
    train_where = period_clause(*train)
    inv_q = quantiles(conn, 'inventory_up_before - inventory_down_before', train_where[0], train_where[1])
    red_q = quantiles(conn, 'abs(inventory_up_before - inventory_down_before) - abs(inventory_up_after - inventory_down_after)', train_where[0], train_where[1])
    after_q = quantiles(conn, 'inventory_up_after - inventory_down_after', train_where[0], train_where[1])

    time_regimes = {}
    for name, (low, high) in TIME_WINDOWS.items():
        clause, args = condition_time(low, high)
        rule = {'where': clause, 'args': args}
        time_regimes[name] = {'window_ms': [low, high], 'train': evaluate_rule(conn, rule, train), 'validation': evaluate_rule(conn, rule, validation), 'oos': evaluate_rule(conn, rule, oos), 'valid_train': valid(evaluate_rule(conn, rule, train))}
    size_regimes = {}
    for name, (low, high) in SIZE_WINDOWS.items():
        clause, args = condition_size(low, high); rule = {'where': clause, 'args': args}
        size_regimes[name] = {'window': [low, high], 'train': evaluate_rule(conn, rule, train), 'validation': evaluate_rule(conn, rule, validation), 'oos': evaluate_rule(conn, rule, oos)}

    inv_regimes = {}
    inv_edges = [('low', None, inv_q['p25']), ('medium', inv_q['p25'], inv_q['p75']), ('high', inv_q['p75'], inv_q['p90']), ('very_high', inv_q['p90'], None)]
    for name, low, high in inv_edges:
        clauses = []; args = []
        if low is not None: clauses.append('abs(inventory_up_before - inventory_down_before) >= ?'); args.append(low)
        if high is not None: clauses.append('abs(inventory_up_before - inventory_down_before) < ?'); args.append(high)
        rule = {'where': ' AND '.join(clauses) or '1=1', 'args': args}
        inv_regimes[name] = {'range': [low, high], 'train': evaluate_rule(conn, rule, train), 'validation': evaluate_rule(conn, rule, validation), 'oos': evaluate_rule(conn, rule, oos)}

    direction = {}
    for name, sides in {'UP->DOWN': ('UP','DOWN'), 'DOWN->UP': ('DOWN','UP')}.items():
        rule = {'where': 'first_side=? AND second_side=?', 'args': list(sides)}
        direction[name] = {'train': evaluate_rule(conn, rule, train), 'validation': evaluate_rule(conn, rule, validation), 'oos': evaluate_rule(conn, rule, oos)}

    candidates = [
        ('C1_FAST_PAIR', combine(condition_time(1000, 5000))),
        ('C2_MEDIUM_PAIR', combine(condition_time(5000, 15000))),
        ('C3_LATE_MEDIUM', combine(condition_time(15000, 30000))),
        ('C4_INVENTORY_REBALANCE', combine(condition_time(5000, 15000), ('abs(inventory_up_before - inventory_down_before) >= ?', [inv_q['p50']]), ('abs(inventory_up_before - inventory_down_before) - abs(inventory_up_after - inventory_down_after) > ?', [0]))),
        ('C5_SMALL_MEDIUM', combine(condition_time(5000, 15000), condition_size(0, 50))),
    ]
    candidate_results = []
    for name, (where, args) in candidates:
        rule = {'name': name, 'where': where, 'args': args}
        entry = {'name': name, 'conditions': where, 'train': evaluate_rule(conn, rule, train), 'validation': evaluate_rule(conn, rule, validation), 'oos': evaluate_rule(conn, rule, oos), 'friction': {}, 'walk_forward': []}
        for friction in FRICTIONS:
            entry['friction'][str(friction)] = {'net_edge_weighted': (entry['oos']['gross_edge_weighted'] - friction) if entry['oos']['gross_edge_weighted'] is not None else None, 'positive_edge_pct': None}
        candidate_results.append(entry)

    weeks = sorted({r[0] for r in conn.execute("SELECT DISTINCT strftime('%Y-W%W', first_timestamp / 1000, 'unixepoch') FROM pair_observations")})
    for entry, (name, (where, args)) in zip(candidate_results, candidates):
        for index in range(2, len(weeks)):
            week_filter = "strftime('%Y-W%W', first_timestamp / 1000, 'unixepoch') = ?"
            entry['walk_forward'].append({'test_week': weeks[index], 'result': metric(conn, f'({where}) AND {week_filter}', args + [weeks[index]])})

    interactions = {}
    for tname, (tlow, thigh) in TIME_WINDOWS.items():
        for sname, (slow, shigh) in SIZE_WINDOWS.items():
            tclause, targs = condition_time(tlow, thigh); sclause, sargs = condition_size(slow, shigh)
            m = metric(conn, f'{tclause} AND {sclause}', targs + sargs)
            if m['pairs'] >= MIN_PAIRS:
                interactions[f'{tname}|{sname}'] = m

    friction = {}
    for name, (where, args) in candidates:
        all_m = metric(conn, where, args)
        friction[name] = {str(f): {'net_edge_weighted': all_m['gross_edge_weighted'] - f if all_m['gross_edge_weighted'] is not None else None} for f in FRICTIONS}

    hedge_completion = {'status': 'NOT_IDENTIFIABLE_FROM_PAIR_OBSERVATIONS', 'reason': 'pair_observations contains completed FIFO pairs only; unmatched first legs are not persisted', 'horizons_seconds': [5,10,15,30,60]}
    summary = {'source': str(DB), 'read_only': True, 'created_utc': datetime.now(timezone.utc).isoformat(), 'baseline': baseline, 'split': {'train': train, 'validation': validation, 'oos': oos}, 'feature_limits': ['No BTC volatility', 'No order-book imbalance', 'No network latency', 'No time-to-expiry'], 'minimum_sample': {'pairs': MIN_PAIRS, 'markets': MIN_MARKETS, 'days': MIN_DAYS, 'weeks': MIN_WEEKS}}
    outputs = {
        'regime_dataset_summary.json': summary,
        'time_regimes.json': {'excluded_subsecond_from_selection': True, 'regimes': time_regimes},
        'size_regimes.json': size_regimes,
        'inventory_regimes.json': {'before_quantiles': inv_q, 'reduction_quantiles': red_q, 'after_quantiles': after_q, 'regimes': inv_regimes},
        'direction_regimes.json': direction,
        'interaction_matrix.json': interactions,
        'train_validation_oos.json': {'candidates': candidate_results, 'selection_rule': 'Candidates fixed from D1 windows and TRAIN-only conditions; OOS not used for selection'},
        'walk_forward.json': {'weeks': weeks, 'candidates': candidate_results},
        'friction_analysis.json': friction,
        'hedge_completion.json': hedge_completion,
        'candidate_strategies.json': candidate_results,
        'champion_v1.json': {'champion': 'NONE', 'reason': 'No promotion while hedge completion is not identifiable and the candidate results are gross, not net.'},
    }
    for filename, data in outputs.items():
        (OUT / filename).write_text(json.dumps(data, indent=2), encoding='utf-8')
    report = report_text(summary, time_regimes, candidate_results, hedge_completion, inv_regimes, direction, weeks)
    (OUT / 'd2_optimal_regime_report.md').write_text(report, encoding='utf-8')
    print(json.dumps({'baseline': baseline, 'candidates': [{'name': x['name'], 'train': x['train'], 'validation': x['validation'], 'oos': x['oos']} for x in candidate_results], 'champion': 'NONE'}, indent=2))
    conn.close()


def report_text(summary, times, candidates, completion, inventory, direction, weeks):
    def fmt(x): return 'N/D' if x is None else f'{x:.6f}'
    lines = ['# BONEREAPER D2 — OPTIMAL REGIME DISCOVERY', '', 'READ-ONLY research analysis. D1 snapshot, matcher and pair database were not modified.', '', '## Baseline', f"- PairCost weighted: **{fmt(summary['baseline']['pair_cost_weighted'])}**", f"- GrossEdge weighted: **{fmt(summary['baseline']['gross_edge_weighted'])}**", f"- Pairs: **{summary['baseline']['pairs']:,}**", '', '## Selection protocol', '- Chronological 60% TRAIN / 20% VALIDATION / 20% OOS.', '- No random split and no OOS tuning.', '- Sub-second observations excluded from primary selection.', '- Minimum: 10,000 pairs, 25 markets, 3 days, 2 weeks.', '- `CHAMPION = NONE` is forced because unmatched first legs are absent and friction-adjusted net performance is not proven.', '', '## Time regimes', '| Window | Train pairs | Train weighted PairCost | Validation weighted PairCost | OOS weighted PairCost | OOS edge weighted |', '|---|---:|---:|---:|---:|---:|']
    for name, v in times.items():
        lines.append(f"| {name} | {v['train']['pairs']:,} | {fmt(v['train']['pair_cost_weighted'])} | {fmt(v['validation']['pair_cost_weighted'])} | {fmt(v['oos']['pair_cost_weighted'])} | {fmt(v['oos']['gross_edge_weighted'])} |")
    lines += ['', '## Candidates', '| Candidate | Train edge | Validation edge | OOS edge | OOS pairs | WF positive windows |', '|---|---:|---:|---:|---:|---:|']
    for c in candidates:
        wf = sum(1 for x in c['walk_forward'] if (x['result'].get('gross_edge_weighted') or 0) > 0 and x['result']['pairs'] >= MIN_PAIRS)
        lines.append(f"| {c['name']} | {fmt(c['train']['gross_edge_weighted'])} | {fmt(c['validation']['gross_edge_weighted'])} | {fmt(c['oos']['gross_edge_weighted'])} | {c['oos']['pairs']:,} | {wf} |")
    lines += ['', '## Inventory', f"- Low/medium/high/very-high inventory regimes are quantile-based; see `inventory_regimes.json`.", f"- Directional reduction is evaluated from persisted before/after fields.", '', '## Direction', f"- UP→DOWN OOS weighted edge: {fmt(direction['UP->DOWN']['oos']['gross_edge_weighted'])}", f"- DOWN→UP OOS weighted edge: {fmt(direction['DOWN->UP']['oos']['gross_edge_weighted'])}", '', '## Hedge completion', '- Status: **NOT IDENTIFIABLE FROM PAIR_OBSERVATIONS**.', '- The database stores completed pairs, not unmatched first legs; completion rates at 5/10/15/30/60 seconds cannot be estimated without an additional first-leg universe.', '', '## Decision', '- **CHAMPION V1: NONE**', '- Reason: the apparent gross edge is not sufficient to establish a tradable regime without first-leg completion, execution friction, slippage and net settlement validation.', '', '## Ten quantitative findings', '1. D1 quantity is preserved as the reference; D2 uses the corrected FIFO database read-only.', '2. Sub-second timing is excluded from selection because public timestamps are second-resolution.', '3. Time windows are evaluated chronologically, not with random splits.', '4. Candidate rules are limited to five simple interpretable rules.', '5. OOS is evaluated after fixed candidate definitions, not used for tuning.', '6. The 5–15 second window is explicitly tested rather than assumed optimal.', '7. Size and time interactions are retained only above the minimum sample threshold.', '8. Direction is evaluated conditionally but does not receive an invented bias.', '9. Walk-forward results are reported per test week.', '10. No candidate is promoted because hedge completion is not identifiable and all edges are gross simulations.', '', '## Limitations', '- FIFO is a reconstruction convention, not Bonereaper internal matching.', '- Fills are not independent decisions and public activity may be incomplete.', '- GrossPairEdge excludes fees, slippage, latency, failed second legs and rebates.', '- No PnL or settlement is computed.', '- No real trading or order execution occurred.']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    d2()
