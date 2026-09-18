import asyncio, os
from pathlib import Path
from app.collectors.binance import BinanceCollector
from app.storage.db import Database

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = os.getenv("DATABASE_PATH", str(ROOT / "data" / "poly_quant.db"))

async def main():
    db = Database(DB_PATH)
    await db.init()
    async def on_tick(tick):
        await db.insert_btc(tick)
        print(f"BTC {tick.price:.2f} recv={tick.recv_ts_ms}")
    collector = BinanceCollector(os.getenv("BINANCE_SYMBOL", "btcusdt"), on_tick)
    await collector.run()

if __name__ == "__main__":
    asyncio.run(main())
