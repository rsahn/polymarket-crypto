"""D4 offline research. Run stages: prepare, develop, finalize (once).

See D4_PROTOCOL.md. Source databases are read-only. No network/order code.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import c3_portfolio_backtest_v4 as v4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'c3_d4_results'
TABLE = 'c3_shadow_observations_v2'
FEATURES = ['first_ask', 'first_bid', 'first_ask_qty', 'first_bid_qty',
            'first_spread', 'opposite_ask', 'opposite_bid', 'opposite_ask_qty',
            'opposite_bid_qty', 'opposite_spread', 'depth_imbalance',
            'btc_return_1s', 'btc_return_5s', 'btc_return_15s', 'time_remaining_ms']
DERIVED = ['opposite_depth_coverage_t0', 'pair_cash_required_t0', 'exit_coverage_t0']
FILTER_FEATURES = [x for x in FEATURES if x != 'first_ask'] + DERIVED
LABELS = ['hedge_ts_ms', 'delay_ms', 'second_ask', 'second_ask_qty']
META = ['id', 'anchor_ts_ms', 'market_slug', 'condition_id', 'market_duration', 'direction']
EPS = 1e-9


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def readonly(path):
    c = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    c.execute('PRAGMA query_only=ON')
    return c


def utc():
    return datetime.now(timezone.utc).isoformat()


def market_manifest(frame):
    m = frame[frame.market_slug.str.fullmatch(r'btc-updown-(5m|15m)-\d{10}', na=False)].copy()
    m = m.sort_values(['first_ts', 'market_slug']).reset_index(drop=True)
    if m.market_slug.duplicated().any() or (m.conditions != 1).any():
        raise ValueError('Ambiguous market identity')
    m['split'] = ['train' if i < int(len(m)*.6) else
                  'validation' if i < int(len(m)*.8) else 'oos' for i in range(len(m))]
    m['market_start_ms'] = m.market_slug.str.rsplit('-', n=1).str[-1].astype('int64')*1000
    duration = m.market_slug.str.extract(r'-(5m|15m)-')[0]
    if not duration.eq(m.market_duration).all():
        raise ValueError('Slug/duration mismatch')
    m['market_end_ms'] = m.market_start_ms + duration.map({'5m': 300000, '15m': 900000})
    # Target 5m intervals must not overlap across partitions.
    t = m[m.market_duration.eq('5m')]
    for a, b in [('train', 'validation'), ('validation', 'oos')]:
        if t[t.split.eq(a)].market_end_ms.max() > t[t.split.eq(b)].market_start_ms.min():
            raise ValueError('Target market windows overlap split boundary')
    return m


def prepare(out):
    out.mkdir(parents=True, exist_ok=True)
    if (out/'manifest.json').exists() or (out/'snapshot.db').exists():
        raise RuntimeError('Prepared run exists; refusing overwrite')
    source = ROOT/'data'/'c3_shadow_live.db'
    with readonly(source) as src, sqlite3.connect(out/'snapshot.db') as dst:
        src.backup(dst)
    with readonly(out/'snapshot.db') as db:
        m = pd.read_sql_query(f'''SELECT market_slug,market_duration,
            min(anchor_ts_ms) first_ts,max(anchor_ts_ms) last_ts,count(*) rows,
            count(distinct condition_id) conditions FROM {TABLE}
            GROUP BY market_slug,market_duration''', db)
    markets = market_manifest(m)
    old = pd.read_csv(ROOT/'analysis/c3_v21_results/market_split.csv')
    if old.market_slug.tolist() != markets.market_slug.tolist():
        raise RuntimeError('Historical split differs; do not recycle old OOS into development')
    markets.to_csv(out/'market_split.csv', index=False)
    protocol = ROOT/'analysis/D4_PROTOCOL.md'
    write_json(out/'manifest.json', {
        'created_utc': utc(), 'source': str(source), 'snapshot_sha256': digest(out/'snapshot.db'),
        'script_sha256': digest(__file__), 'protocol_sha256': digest(protocol),
        'split_sha256': digest(out/'market_split.csv'),
        'total_rows': int(m.rows.sum()), 'real_slug_rows': int(markets.rows.sum()),
        'excluded_legacy_rows': int(m.rows.sum()-markets.rows.sum()),
        'real_markets': len(markets), 'matches_historical_split': True,
        'historical_oos_previously_used': True,
        'data_quality_promotion_block': True,
        'features': FEATURES + DERIVED, 'label_columns': LABELS,
        'initial_capital': 500, 'leg1_budget': 10, 'friction': .005,
    })
    print('Prepared metadata only:', markets.groupby(['split','market_duration']).size().to_dict())


def check_integrity(out):
    m = read_json(out/'manifest.json')
    for key, path in [('script_sha256', __file__), ('snapshot_sha256', out/'snapshot.db'),
                      ('protocol_sha256', ROOT/'analysis/D4_PROTOCOL.md'),
                      ('split_sha256', out/'market_split.csv')]:
        if digest(path) != m[key]:
            raise RuntimeError(f'Frozen input changed: {key}')
    return m


def load_partition(out, split, *, oos_token=False):
    if split not in ('train', 'validation', 'oos'):
        raise ValueError(split)
    if split == 'oos' and not oos_token:
        raise RuntimeError('OOS can only be loaded in finalize after rule freeze')
    markets = pd.read_csv(out/'market_split.csv')
    markets = markets[markets.split.eq(split) & markets.market_duration.eq('5m')]
    slugs = markets.market_slug.tolist()
    with readonly(out/'snapshot.db') as db:
        df = pd.read_sql_query(f'''SELECT {','.join(META+FEATURES+LABELS)} FROM {TABLE}
            WHERE market_slug IN ({','.join('?' for _ in slugs)})
              AND market_duration='5m' AND direction='DOWN->UP'
            ORDER BY anchor_ts_ms,id''', db, params=slugs)
    df['market_start_ms'] = df.market_slug.map(markets.set_index('market_slug').market_start_ms)
    df['market_end_ms'] = df.market_slug.map(markets.set_index('market_slug').market_end_ms)
    outside = ~((df.anchor_ts_ms >= df.market_start_ms) & (df.anchor_ts_ms < df.market_end_ms))
    df.loc[outside, META+['market_start_ms','market_end_ms']].to_csv(
        out/f'{split}_invalid_anchor_times.csv', index=False)
    return add_features(df), len(markets)


def add_features(df):
    df = df.copy()
    target = np.minimum(10/df.first_ask.where(df.first_ask > 0), df.first_ask_qty)
    df['opposite_depth_coverage_t0'] = df.opposite_ask_qty/target
    df['pair_cash_required_t0'] = target*(df.first_ask+df.opposite_ask+.005)
    df['exit_coverage_t0'] = df.first_bid_qty/target
    return df


def entry_signals(df, rule=None):
    """Only T0 whitelist is visible here, even when caller has future labels."""
    x = df[META + FEATURES + DERIVED + ['market_start_ms', 'market_end_ms']]
    mask = (x.market_duration.eq('5m') & x.direction.eq('DOWN->UP') &
            x.first_ask.gt(0) & x.first_ask.le(.14) & x.first_ask_qty.gt(0) &
            x.anchor_ts_ms.ge(x.market_start_ms) & x.anchor_ts_ms.lt(x.market_end_ms))
    if rule is not None:
        f, op, threshold = rule['feature'], rule['operator'], rule['threshold']
        if f not in FILTER_FEATURES or op not in ('>=', '<=') or not math.isfinite(threshold):
            raise ValueError('Filter outside T0 whitelist')
        values = x[f]
        mask &= np.isfinite(values) & (values.ge(threshold) if op == '>=' else values.le(threshold))
    last, selected = {}, []
    for r in x[mask].sort_values(['anchor_ts_ms', 'id']).itertuples():
        if r.anchor_ts_ms-last.get(r.market_slug, -10**20) >= 15000:
            selected.append(r.Index)
            last[r.market_slug] = r.anchor_ts_ms
    return df.loc[selected].copy()


def valid_hedge(r):
    dt = r['hedge_ts_ms']-r['anchor_ts_ms']
    return (15000 <= dt <= 30000 and dt == r['delay_ms'] and
            r['hedge_ts_ms'] < r['market_end_ms'] and
            math.isfinite(r['second_ask']) and 0 < r['second_ask'] <= 1 and
            math.isfinite(r['second_ask_qty']) and r['second_ask_qty'] > 0)


def status(q1, paired):
    return 'impossible' if paired <= EPS else 'complete' if paired >= q1-EPS else 'reduced'


def simulate(signals, exit_mode='v4_proxy', initial=500., budget=10.):
    """Event replay: no future quote is read for a LEG1 decision or sizing."""
    if exit_mode not in ('v4_proxy', 'zero_recovery'):
        raise ValueError(exit_mode)
    cash, peak, maxdd, maxddpct = initial, initial, 0., 0.
    pending, hedged, ledger, events, curve, used_depth = {}, {}, [], [], [], {}
    skipped = 0
    rows = signals.to_dict('records')
    for i, r in enumerate(rows):
        heapq.heappush(events, (int(r['anchor_ts_ms']), 2, i))

    def depth(key, available, requested):
        capacity = max(0., available-used_depth.get(key, 0.))
        filled = min(max(0., requested), capacity)
        used_depth[key] = used_depth.get(key, 0.)+filled
        return filled

    while events:
        now, kind, i = heapq.heappop(events)
        r = rows[i]
        if kind == 2:
            # No reference to second_ask/qty here.
            q1 = depth((r['market_slug'], now, 'down_ask'), float(r['first_ask_qty']),
                       min(budget/r['first_ask'], max(0., cash)/r['first_ask']))
            if q1 <= EPS:
                skipped += 1
                continue
            cost = q1*r['first_ask']
            cash -= cost
            pending[i] = {'id': r['id'], 'market_slug': r['market_slug'],
                          'anchor_ts_ms': now, 'market_end_ms': r['market_end_ms'],
                          'q1': q1, 'leg1_cost': cost, 'cash_before_leg1': cash+cost}
            # Scheduling a historical observation is replay infrastructure, not an input.
            when = int(r['hedge_ts_ms']) if valid_hedge(r) else min(now+30000, int(r['market_end_ms']))
            heapq.heappush(events, (when, 1, i))
        elif kind == 1:
            trade = pending.pop(i)
            q1 = trade['q1']
            valid = valid_hedge(r)
            p2 = r['second_ask'] if valid else 0.
            book = r['second_ask_qty'] if valid else 0.
            qcash = max(0., cash)/(p2+.005)
            key = (r['market_slug'], now, 'up_ask')
            available = max(0., book-used_depth.get(key, 0.))
            paired = depth(key, book, min(q1, qcash))
            unhedged = q1-paired
            exit_qty = 0.
            # Proxy from V4; deliberately not represented as an observed future fill.
            if exit_mode == 'v4_proxy' and unhedged > EPS:
                bid, bidqty = r['first_bid'], r['first_bid_qty']
                if math.isfinite(bid) and 0 <= bid < r['first_ask'] and math.isfinite(bidqty):
                    exit_qty = depth((r['market_slug'], r['anchor_ts_ms'], 'down_bid_proxy'),
                                     max(0., bidqty), unhedged)
            proceeds = exit_qty*r['first_bid'] if exit_qty else 0.
            leg2_cost = paired*(p2+.005)
            cash += proceeds-leg2_cost
            trade.update(hedge_ts_ms=now, paired_qty=paired, unhedged_qty=unhedged,
                         exit_qty=exit_qty, zero_value_qty=unhedged-exit_qty,
                         exit_proceeds=proceeds, leg2_with_friction=leg2_cost,
                         total_cost=trade['leg1_cost']+leg2_cost,
                         pair_net_edge=1-r['first_ask']-p2-.005 if valid else None,
                         status=status(q1, paired), invalid_future_quote=not valid,
                         cash_limited=qcash < min(q1, available)-EPS,
                         depth_limited=available < q1-EPS,
                         cash_at_hedge_before_exit=cash-proceeds+leg2_cost,
                         pnl=paired+proceeds-trade['leg1_cost']-leg2_cost)
            hedged[i] = trade
            heapq.heappush(events, (int(r['market_end_ms']), 0, i))
        else:
            trade = hedged.pop(i)
            cash += trade['paired_qty']
            ledger.append(trade)
        if cash < -1e-7:
            raise AssertionError('Negative cash')
        equity = cash+sum(p['paired_qty'] for p in hedged.values())
        peak = max(peak, equity)
        maxdd = max(maxdd, peak-equity)
        maxddpct = max(maxddpct, (peak-equity)/peak*100)
        curve.append({'ts_ms': now, 'event': kind, 'cash': cash, 'equity_lower_bound': equity})
    ld = pd.DataFrame(ledger)
    assert not pending and not hedged
    assert abs((float(ld.pnl.sum()) if len(ld) else 0)-(cash-initial)) < 1e-6
    mk = (ld.groupby('market_slug', as_index=False).agg(
        trades=('pnl', 'size'), pnl=('pnl', 'sum'),
        complete=('status', lambda x: int(x.eq('complete').sum())),
        reduced=('status', lambda x: int(x.eq('reduced').sum())),
        impossible=('status', lambda x: int(x.eq('impossible').sum()))) if len(ld) else pd.DataFrame(
            columns=['market_slug', 'trades', 'pnl', 'complete', 'reduced', 'impossible']))
    metrics = summarize(signals, ld, mk, cash, maxdd, maxddpct, skipped, initial)
    return metrics, ld, mk, pd.DataFrame(curve)


def summarize(signals, ld, mk, cash, maxdd, maxddpct, skipped, initial):
    n = len(ld)
    counts = ld.status.value_counts().to_dict() if n else {}
    profits = mk.pnl.to_numpy(dtype=float)
    positive = float(profits[profits > EPS].sum())
    best = float(profits.max()) if len(profits) else 0.
    paired = float(ld.paired_qty.sum()) if n else 0.
    pair_pnl = float((ld.paired_qty*pd.to_numeric(ld.pair_net_edge).fillna(0)).sum()) if n else 0.
    return {
        'signals': len(signals), 'signal_markets': int(signals.market_slug.nunique()),
        'trades': n, 'markets_traded': len(mk), 'initial_capital': initial,
        'final_capital': cash, 'pnl': cash-initial, 'return_pct': (cash/initial-1)*100,
        'max_drawdown': maxdd, 'max_drawdown_pct': maxddpct, 'skipped_no_cash': skipped,
        **{f'hedge_{s}': int(counts.get(s, 0)) for s in ('complete', 'reduced', 'impossible')},
        'completion_rate': counts.get('complete', 0)/n if n else None,
        'failure_rate': counts.get('impossible', 0)/n if n else None,
        'incomplete_rate': (n-counts.get('complete', 0))/n if n else None,
        'net_edge_paired': pair_pnl/paired if paired > EPS else None,
        'pnl_per_trade': (cash-initial)/n if n else None,
        'paired_pnl': pair_pnl, 'unhedged_pnl': cash-initial-pair_pnl,
        'winning_markets': int((profits > EPS).sum()), 'losing_markets': int((profits < -EPS).sum()),
        'flat_markets': int((abs(profits) <= EPS).sum()),
        'best_market_pnl': best, 'worst_market_pnl': float(profits.min()) if len(profits) else 0.,
        'pnl_ex_best_market': cash-initial-best,
        'top_market_share_positive_pnl': best/positive if positive > EPS else None,
        'cash_limited': int(ld.cash_limited.sum()) if n else 0,
        'depth_limited': int(ld.depth_limited.sum()) if n else 0,
        'invalid_future_quotes': int(ld.invalid_future_quote.sum()) if n else 0,
    }


def gates(m, base, split):
    return (m['markets_traded'] >= (20 if split == 'train' else 5) and
            m['trades'] >= (50 if split == 'train' else 20) and m['pnl'] > 0 and
            m['pnl_ex_best_market'] > 0 and m['winning_markets']/m['markets_traded'] >= .5 and
            m['completion_rate'] >= max(.8, base['completion_rate'] or 0) and
            m['failure_rate'] <= .05 and m['max_drawdown_pct'] <= 20)


def candidate_rules(train):
    # Discovery thresholds from T0 D3 TRAIN signals only.
    x = entry_signals(train)
    rules = []
    for f in FILTER_FEATURES:
        values = x[f].replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty or values.nunique() < 2:
            continue
        for threshold in sorted(set(float(v) for v in values.quantile([.25,.5,.75]))):
            for op in ('<=', '>='):
                rules.append({'feature': f, 'operator': op, 'threshold': threshold})
    for threshold in (1., 2.):
        r = {'feature': 'opposite_depth_coverage_t0', 'operator': '>=', 'threshold': threshold}
        if r not in rules:
            rules.append(r)
    return rules


def bootstrap_market(mk):
    if mk.empty:
        return {'mean_market_pnl_95pct': None}
    values = mk.pnl.to_numpy()
    rng = np.random.default_rng(20260920)
    means = rng.choice(values, size=(2000, len(values)), replace=True).mean(axis=1)
    return {'mean_market_pnl_95pct': np.quantile(means, [.025,.975]).tolist(),
            'method': 'IID market bootstrap; descriptive, serial dependence may remain'}


def diagnostics(signals, ledger, out, prefix):
    records = []
    for r in signals.to_dict('records'):
        q1 = min(10/r['first_ask'], r['first_ask_qty'])
        qp = min(q1, r['second_ask_qty']) if valid_hedge(r) else 0.
        records.append({'id': r['id'], 'book_label': status(q1, qp)})
    labels = pd.DataFrame(records, columns=['id','book_label'])
    x = signals.merge(labels, on='id', how='left')
    if not ledger.empty:
        x = x.merge(ledger[['id','status']], on='id', how='left')
    else:
        x['status'] = None
    rows = []
    for label in ('book_label', 'status'):
        for cls in ('complete','reduced','impossible'):
            sub = x[x[label].eq(cls)]
            for f in FEATURES+DERIVED:
                values = sub[f].replace([np.inf,-np.inf], np.nan)
                quantiles = values.dropna().quantile([.25,.5,.75])
                rows.append({'label': label, 'class': cls, 'feature': f, 'signals': len(sub),
                             'markets': sub.market_slug.nunique(), 'missing': int(values.isna().sum()),
                             **{name: (float(v) if pd.notna(v) else None)
                                for name, v in zip(('q25','median','q75'), quantiles)}})
    pd.DataFrame(rows).to_csv(out/f'{prefix}_feature_comparison.csv', index=False)
    x[['id','market_slug','anchor_ts_ms','book_label','status']].to_csv(
        out/f'{prefix}_labels.csv', index=False)


def evaluate(df, out=None, prefix=None):
    result = {}
    for mode in ('v4_proxy', 'zero_recovery'):
        m, ld, mk, curve = simulate(df, mode)
        if out is not None:
            ld.to_csv(out/f'{prefix}_{mode}_ledger.csv', index=False)
            mk.to_csv(out/f'{prefix}_{mode}_markets.csv', index=False)
            curve.to_csv(out/f'{prefix}_{mode}_equity.csv', index=False)
            m.update(bootstrap_market(mk))
            if mode == 'v4_proxy':
                diagnostics(df, ld, out, prefix)
        result[mode] = m
    return result


def develop(out):
    check_integrity(out)
    if (out/'frozen_rule.json').exists():
        raise RuntimeError('Rule already frozen; development is closed')
    train, ntrain = load_partition(out, 'train')
    base_train = evaluate(entry_signals(train), out, 'train_baseline')
    rules = candidate_rules(train)
    candidates = []
    for i, rule in enumerate(rules):
        results = evaluate(entry_signals(train, rule))
        passed = all(gates(results[mode], base_train[mode], 'train') for mode in results)
        candidates.append({'candidate_id': i, 'rule': rule, 'train': results, 'train_pass': passed})
    write_json(out/'train_candidates.json', candidates)
    eligible = [c for c in candidates if c['train_pass']]
    eligible.sort(key=lambda c: (-c['train']['zero_recovery']['pnl'],
                                -c['train']['zero_recovery']['completion_rate'],
                                -c['train']['zero_recovery']['markets_traded'], c['candidate_id']))
    nominee = eligible[0] if eligible else None
    # Write nomination BEFORE reading any validation label.
    write_json(out/'train_nomination.json', {'nominee': nominee, 'candidate_count': len(candidates),
                                           'eligible_count': len(eligible), 'utc': utc()})
    validation, nval = load_partition(out, 'validation')
    base_val = evaluate(entry_signals(validation), out, 'validation_baseline')
    passed_val = False
    selected_metrics = {}
    if nominee:
        for name, df in [('train', train), ('validation', validation)]:
            selected_metrics[name] = evaluate(entry_signals(df, nominee['rule']), out, name+'_nominee')
        passed_val = all(gates(selected_metrics['validation'][mode], base_val[mode], 'validation')
                         for mode in base_val)
    # Legacy V4 for development partitions only, never mutate its source/results.
    references = {}
    for name, df in [('train', train), ('validation', validation)]:
        sig = entry_signals(df)
        try:
            references[name] = v4.simulate(sig, 10.)[0]
        except RuntimeError as exc:
            references[name] = {'error': str(exc)}
    write_json(out/'development.json', {
        'market_counts': {'train': ntrain, 'validation': nval},
        'baselines': {'train': base_train, 'validation': base_val},
        'legacy_v4_reference': references, 'nominee_metrics': selected_metrics,
        'candidates': len(candidates), 'train_passed': len(eligible), 'validation_passed': passed_val,
    })
    frozen = {'frozen_utc': utc(), 'policy': 'FILTER' if passed_val else 'NO_TRADE',
              'rule': nominee['rule'] if passed_val else None,
              'reason': 'TRAIN_AND_VALIDATION_PASSED' if passed_val else
                        'NO_TRAIN_CANDIDATE' if not nominee else 'VALIDATION_FAILED',
              'manifest_sha256': digest(out/'manifest.json'),
              'development_sha256': digest(out/'development.json'),
              'nomination_sha256': digest(out/'train_nomination.json'),
              'candidates_sha256': digest(out/'train_candidates.json'),
              'paper_allowed': False, 'data_quality_block': True}
    write_json(out/'frozen_rule.json', frozen)
    print(json.dumps(frozen, indent=2))


def finalize(out):
    check_integrity(out)
    frozen = read_json(out/'frozen_rule.json')
    for key, file in [('manifest_sha256','manifest.json'), ('development_sha256','development.json'),
                      ('nomination_sha256','train_nomination.json'), ('candidates_sha256','train_candidates.json')]:
        if digest(out/file) != frozen[key]:
            raise RuntimeError('Frozen selection inputs changed')
    with (out/'finalization_started.json').open('x', encoding='utf-8') as f:
        json.dump({'utc': utc(), 'frozen_rule_sha256': digest(out/'frozen_rule.json')}, f)
    if frozen['policy'] == 'NO_TRADE':
        result = {'decision': 'NO EDGE', 'oos_opened': False, 'oos_results': None,
                  'reason': frozen['reason'], 'paper_allowed': False,
                  'abstention_portfolio': {'initial': 500, 'final': 500, 'pnl': 0,
                                          'drawdown': 0, 'trades': 0}}
    else:
        # Exclusive durable marker is written BEFORE the only OOS load.
        with (out/'oos_opened.json').open('x', encoding='utf-8') as f:
            json.dump({'utc': utc(), 'frozen_rule_sha256': digest(out/'frozen_rule.json')}, f)
        df, markets = load_partition(out, 'oos', oos_token=True)
        results = evaluate(entry_signals(df, frozen['rule']), out, 'oos_frozen')
        result = {'decision': 'NO EDGE', 'oos_opened': True, 'oos_results': results,
                  'oos_markets': markets, 'paper_allowed': False,
                  'reason': 'HISTORICAL_HOLDOUT_AND_EXECUTION_DATA_NOT_PROSPECTIVELY_VALIDATED'}
    write_json(out/'final.json', result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare','develop','finalize'])
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    {'prepare': prepare, 'develop': develop, 'finalize': finalize}[args.stage](args.out.resolve())


if __name__ == '__main__':
    main()
