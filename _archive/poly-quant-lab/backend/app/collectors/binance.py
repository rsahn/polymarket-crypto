import asyncio, json, time
import websockets
from app.models import MarketTick

class BinanceCollector:
    """Public market-data collector. No account/API key required."""
    def __init__(self, symbol: str, on_tick):
        self.symbol = symbol.lower()
        self.on_tick = on_tick
        self.url = f"wss://stream.binance.com:9443/stream?streams={self.symbol}@aggTrade/{self.symbol}@bookTicker"
        self.last_bid = self.last_ask = self.last_bq = self.last_aq = None

    async def run(self):
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as ws:
                    backoff = 1
                    async for raw in ws:
                        recv = time.time_ns() // 1_000_000
                        msg = json.loads(raw)
                        data = msg.get("data", msg)
                        etype = data.get("e")
                        if etype == "aggTrade":
                            tick = MarketTick("binance", self.symbol, data.get("E"), recv, float(data["p"]), self.last_bid, self.last_ask, self.last_bq, self.last_aq)
                            await self.on_tick(tick)
                        elif etype == "bookTicker" or {"b","a"}.issubset(data):
                            self.last_bid, self.last_ask = float(data["b"]), float(data["a"])
                            self.last_bq, self.last_aq = float(data.get("B",0)), float(data.get("A",0))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[binance] reconnect after error: {exc}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
