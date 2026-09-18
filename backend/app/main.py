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
    stats = {'btc': 0, 'poly': 0, 'latencies': [], 'latest_btc': None, 'latest': {}}

    async def on_tick(tick):
        await db.insert_btc(tick)
        stats['btc'] += 1
        stats['latest_btc'] = tick

    async def on_quote(snapshot):
        await db.insert_poly_snapshot(snapshot)
        stats['poly'] += 1
        stats['latest'][snapshot['market_key']] = snapshot
        await paper.record_snapshot(snapshot, stats['latest_btc'].price if stats['latest_btc'] else None, int(time.time() * 1000))
        if snapshot.get('event_ts_ms'):
            stats['latencies'].append(snapshot['recv_ts_ms'] - snapshot['event_ts_ms'])

    async def control_output():
        while True:
            await asyncio.sleep(1)
            btc = stats['latest_btc']
            if not btc:
                continue
            lines = [f'BTC LIVE: {btc.price:.2f} | Binance WS: CONNECTED | Polymarket WS: CONNECTED']
            for key in ('5m', '15m'):
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
            latency = f"{sum(stats['latencies']) / len(stats['latencies']):.0f}ms" if stats['latencies'] else 'n/a'
            lines.append(f"SQLite: OK | BTC ticks: {stats['btc']} | snapshots: {stats['poly']} | latency: {latency}")
            print('\n'.join(lines))

    collector = BinanceCollector(os.getenv("BINANCE_SYMBOL", "btcusdt"), on_tick)
    markets = PolymarketMarketDiscovery.get_active_btc_markets()
    if not markets:
        print('Polymarket WS: NOT STARTED - no live BTC 5m/15m markets discovered')
    tasks = [asyncio.create_task(collector.run()), asyncio.create_task(control_output())]
    for market in markets:
        tasks.append(asyncio.create_task(PolymarketOrderbookCollector(
            market['market_key'], market['token_ids'], on_quote, market.get('expiry_ts_ms')
        ).run()))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
