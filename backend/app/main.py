import asyncio, os, time
from pathlib import Path
from app.collectors.binance import BinanceCollector
from app.collectors.polymarket import PolymarketMarketDiscovery
from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from app.paper.live import ChampionV1, PaperAudit
from app.storage.db import Database

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = os.getenv("DATABASE_PATH", str(ROOT / "data" / "poly_quant.db"))
PAPER_DB_PATH = os.getenv("PAPER_DATABASE_PATH", str(ROOT / "data" / "paper_live.db"))
CHAMPION_PATH = Path(os.getenv("CHAMPION_PATH", str(ROOT / "analysis" / "bonereaper" / "d2" / "champion_v1.json")))

async def main():
    db = Database(DB_PATH)
    await db.init()
    champion = ChampionV1.load(CHAMPION_PATH)
    paper = PaperAudit(
        Path(PAPER_DB_PATH),
        float(os.getenv("MAX_PAPER_CAPITAL", "500.0")),
        os.getenv("PAPER_SHADOW", "true").lower() == "true",
        champion,
    )
    await paper.init(int(time.time() * 1000))
    print(f'PAPER LIVE: mode={"SHADOW" if paper.shadow else "ACTIVE"} | equity={paper.initial_equity:.2f} USDC | champion={champion.name}')
    if not champion.validated:
        print(f'CHAMPION_NOT_VALIDATED: {champion.reason}')
    stats = {'btc': 0, 'poly': 0, 'latest_btc': None, 'latest': {}, 'states': {'5m': 'WAITING_BOOK', '15m': 'WAITING_BOOK'}, 'metrics': {}, 'rotations': {'5m': 0, '15m': 0}}

    async def on_tick(tick):
        await db.insert_btc(tick)
        stats['btc'] += 1
        stats['latest_btc'] = tick

    async def on_quote(snapshot):
        if snapshot.get('time_remaining_ms') is not None and snapshot['time_remaining_ms'] <= 0:
            return
        up, down = snapshot.get('up') or {}, snapshot.get('down') or {}
        if any(up.get(field) is None for field in ('bid', 'ask')) or any(down.get(field) is None for field in ('bid', 'ask')):
            return
        await db.insert_poly_snapshot(snapshot)
        stats['poly'] += 1
        stats['latest'][snapshot['market_key']] = snapshot
        now_ms = int(time.time() * 1000)
        stats['metrics'][snapshot['market_key']] = {
            'feed_age_ms': now_ms - snapshot['event_ts_ms'] if snapshot.get('event_ts_ms') else None,
            'processing_latency_ms': max(0, now_ms - snapshot['recv_ts_ms']),
            'decision_latency_ms': 0,
            'websocket_rtt_ms': None,
        }
        await paper.record_snapshot(snapshot, stats['latest_btc'].price if stats['latest_btc'] else None, now_ms)

    async def control_output():
        while True:
            await asyncio.sleep(1)
            btc = stats['latest_btc']
            if not btc:
                continue
            lines = [f'BTC LIVE: {btc.price:.2f} | Binance WS: CONNECTED | Polymarket WS: CONNECTED']
            for key in ('5m', '15m'):
                lines.append(f'BTC {key.upper()} STATE: {stats["states"].get(key, "WAITING_BOOK")}')
                snap = stats['latest'].get(key)
                if not snap:
                    lines.append(f'BTC {key.upper()}: waiting for live order book')
                    continue
                up, down = snap.get('up', {}), snap.get('down', {})
                remaining = snap.get('time_remaining_ms')
                remaining_text = f'{remaining / 1000:.0f}s' if remaining is not None else 'n/a'
                lines.append(
                    f"BTC {key.upper()}: UP {up.get('bid')} / {up.get('ask')} "
                    f"(qty {up.get('bid_qty')}/{up.get('ask_qty')}) | DOWN {down.get('bid')} / {down.get('ask')} "
                    f"(qty {down.get('bid_qty')}/{down.get('ask_qty')}) | "
                    f"spread UP {((up.get('ask') or 0) - (up.get('bid') or 0)) if up.get('ask') is not None and up.get('bid') is not None else 'n/a'} | "
                    f"spread DOWN {((down.get('ask') or 0) - (down.get('bid') or 0)) if down.get('ask') is not None and down.get('bid') is not None else 'n/a'} | remaining {remaining_text}"
                )
                metrics = stats['metrics'].get(key, {})
                lines.append(
                    f"{key.upper()} metrics: websocket_rtt_ms={metrics.get('websocket_rtt_ms', 'n/a')} "
                    f"feed_age_ms={metrics.get('feed_age_ms', 'n/a')} "
                    f"processing_latency_ms={metrics.get('processing_latency_ms', 'n/a')} "
                    f"decision_latency_ms={metrics.get('decision_latency_ms', 'n/a')}"
                )
            lines.append(f"SQLite: OK | BTC ticks: {stats['btc']} | snapshots: {stats['poly']}")
            print('\n'.join(lines))

    async def rotate_market(market_key):
        previous_slug = None
        while True:
            print(f'ROTATING {market_key}')
            markets = PolymarketMarketDiscovery.get_active_btc_markets()
            market = next((item for item in markets if item.get('market_key') == market_key and item.get('expiry_ts_ms', 0) > int(time.time() * 1000)), None)
            if market is None or market.get('slug') == previous_slug:
                print(f'WAITING_BOOK {market_key}: no fresh active market')
                await asyncio.sleep(5)
                continue
            previous_slug = market['slug']
            condition_id = (market.get('metadata') or {}).get('conditionId', market['slug'])
            print(f'NEW MARKET {market_key}: slug={market["slug"]} conditionId={condition_id} tokens={market["token_ids"]}')
            state = 'WAITING_BOOK'
            stats['states'][market_key] = state

            async def on_rotated_quote(snapshot):
                nonlocal state
                if snapshot.get('time_remaining_ms') is not None and snapshot['time_remaining_ms'] <= 0:
                    state = 'EXPIRED'
                    stats['states'][market_key] = state
                    print('STALE MARKET TRADING BLOCKED')
                    return
                up, down = snapshot.get('up') or {}, snapshot.get('down') or {}
                if any(up.get(field) is None for field in ('bid', 'ask')) or any(down.get(field) is None for field in ('bid', 'ask')):
                    state = 'WAITING_BOOK'
                    stats['states'][market_key] = state
                    print('STALE MARKET TRADING BLOCKED')
                    return
                if state != 'ACTIVE':
                    state = 'ACTIVE'
                    stats['states'][market_key] = state
                    print(f'ACTIVE {market_key}: slug={market["slug"]} tokens={market["token_ids"]}')
                await on_quote(snapshot)

            await PolymarketOrderbookCollector(
                market_key, market['token_ids'], on_rotated_quote, market.get('expiry_ts_ms')
            ).run()
            stats['states'][market_key] = 'EXPIRED'
            stats['rotations'][market_key] += 1
            stats['latest'].pop(market_key, None)
            stats['metrics'].pop(market_key, None)
            print(f'EXPIRED {market_key}: slug={market["slug"]} tokens={market["token_ids"]}')
            if market_key == '5m' and stats['rotations'][market_key] >= 2:
                print('5M ROTATION OK')
            if market_key == '15m' and stats['rotations'][market_key] >= 1:
                print('15M ROTATION OK')

    collector = BinanceCollector(os.getenv("BINANCE_SYMBOL", "btcusdt"), on_tick)
    tasks = [asyncio.create_task(collector.run()), asyncio.create_task(control_output())]
    tasks.extend(asyncio.create_task(rotate_market(key)) for key in ('5m', '15m'))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
