import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'analysis_bonereaper_snapshot.db'
OUT = ROOT / 'analysis' / 'bonereaper' / 'economic_reconstruction.json'
METADATA = ROOT / 'analysis' / 'bonereaper' / 'market_metadata.json'


def main():
    metadata = json.loads(METADATA.read_text(encoding='utf-8')) if METADATA.exists() else {}
    conn = sqlite3.connect(f'file:{SNAPSHOT}?mode=ro', uri=True)
    fills = conn.execute('''SELECT condition_id,timestamp,side,outcome,size,price,usdc_size,slug,title
                           FROM benchmark_activity WHERE benchmark='Bonereaper'
                           ORDER BY condition_id,timestamp,id''')
    markets = {}
    current = None
    state = None
    total_buy = total_sell = 0.0
    paired_qty = 0.0
    hedge_times = []
    pair_costs = []
    inventory_rows = 0

    def finish():
        if current is None:
            return
        up = max(state['inventory']['UP'], 0.0)
        down = max(state['inventory']['DOWN'], 0.0)
        market = metadata.get(state['slug'], {})
        winner = None
        outcomes = market.get('outcomes')
        prices = market.get('outcome_prices')
        try:
            outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
            prices = json.loads(prices) if isinstance(prices, str) else prices
            if market.get('closed') and outcomes and prices and len(outcomes) == len(prices):
                settled = [str(outcome).upper() for outcome, price in zip(outcomes, prices) if float(price) >= 0.999]
                if len(settled) == 1 and settled[0] in ('UP', 'DOWN'):
                    winner = settled[0]
        except (TypeError, ValueError, json.JSONDecodeError):
            winner = None
        pnl = state['cashflow'] + (state['inventory'].get(winner, 0.0) if winner else 0.0)
        markets[current] = {
            'condition_id': current,
            'slug': state['slug'],
            'fills': state['fills'],
            'entry_time': state['first'],
            'first_timestamp': state['first'],
            'last_timestamp': state['last'],
            'inventory_up': up,
            'inventory_down': down,
            'paired_inventory': min(up, down),
            'directional_up': max(up - down, 0.0),
            'directional_down': max(down - up, 0.0),
            'inventory_imbalance': up - down,
            'average_up_price': state['cost']['UP'] / state['bought']['UP'] if state['bought']['UP'] else None,
            'average_down_price': state['cost']['DOWN'] / state['bought']['DOWN'] if state['bought']['DOWN'] else None,
            'market_open_time': market.get('start_time'),
            'market_expiry_time': market.get('expiry_time'),
            'settlement_status': 'SETTLED' if winner else ('CLOSED_UNPROVEN' if market.get('closed') else 'OPEN_OR_UNKNOWN'),
            'resolution': winner,
            'pnl': pnl if winner else None,
            'pnl_status': 'SETTLEMENT_CONFIRMED' if winner else 'NOT_COMPUTABLE_WITH_CURRENT_PUBLIC_ACTIVITY',
        }

    for row in fills:
        condition, ts, side, outcome, size, price, usdc, slug, title = row
        if condition != current:
            finish()
            current = condition
            state = {'fills': 0, 'first': ts, 'last': ts, 'slug': slug or '', 'cashflow': 0.0, 'inventory': {'UP': 0.0, 'DOWN': 0.0}, 'cost': {'UP': 0.0, 'DOWN': 0.0}, 'bought': {'UP': 0.0, 'DOWN': 0.0}, 'last_inventory_increase': {'UP': None, 'DOWN': None}}
        outcome = (outcome or '').upper()
        side = (side or '').upper()
        size = float(size or 0.0); price = float(price or 0.0)
        state['fills'] += 1; state['last'] = ts; inventory_rows += 1
        if outcome not in ('UP', 'DOWN') or side not in ('BUY', 'SELL'):
            continue
        before_paired = min(max(state['inventory']['UP'], 0.0), max(state['inventory']['DOWN'], 0.0))
        if side == 'BUY':
            state['inventory'][outcome] += size
            state['cost'][outcome] += size * price
            state['bought'][outcome] += size
            state['last_inventory_increase'][outcome] = ts
            total_buy += size
            state['cashflow'] -= size * price
        else:
            state['inventory'][outcome] -= size
            total_sell += size
            state['cashflow'] += size * price
        after_paired = min(max(state['inventory']['UP'], 0.0), max(state['inventory']['DOWN'], 0.0))
        newly_paired = max(0.0, after_paired - before_paired)
        if newly_paired and side == 'BUY':
            opposite = 'DOWN' if outcome == 'UP' else 'UP'
            opposite_avg = state['cost'][opposite] / state['bought'][opposite] if state['bought'][opposite] else None
            paired_qty += newly_paired
            first_leg_ts = state['last_inventory_increase'][opposite]
            if first_leg_ts is not None:
                hedge_times.append(max(0, ts - first_leg_ts))
            if opposite_avg is not None:
                pair_costs.append(price + opposite_avg)

    finish(); conn.close()
    market_values = list(markets.values())
    output = {
        'snapshot': str(SNAPSHOT),
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'fills_processed': inventory_rows,
        'markets': len(market_values),
        'total_buy_contracts': total_buy,
        'total_sell_contracts': total_sell,
        'paired_quantity_net_inventory_observed': paired_qty,
        'hedge_rate_net_inventory_observed': paired_qty / total_buy if total_buy else None,
        'time_to_hedge_seconds': {'count': len(hedge_times), 'median': sorted(hedge_times)[len(hedge_times)//2] if hedge_times else None},
        'pair_cost': {'count': len(pair_costs), 'mean': sum(pair_costs)/len(pair_costs) if pair_costs else None, 'median': sorted(pair_costs)[len(pair_costs)//2] if pair_costs else None},
        'pnl': None,
        'pnl_status': 'NOT_COMPUTABLE_WITHOUT_MARKET_RESOLUTION_AND_SETTLEMENT',
        'markets_sample': market_values[:1000],
    }
    OUT.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps({k: output[k] for k in ('fills_processed','markets','paired_quantity_net_inventory_observed','hedge_rate_net_inventory_observed','time_to_hedge_seconds','pair_cost','pnl_status')}, indent=2))


if __name__ == '__main__':
    main()
