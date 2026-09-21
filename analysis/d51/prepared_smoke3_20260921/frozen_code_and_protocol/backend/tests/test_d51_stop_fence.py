import asyncio, sqlite3, tempfile, time, unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.d5.live import run
from app.d5.store import decode
from app.models import MarketTick
from test_d5 import snapshot

class StopFenceTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, requested):
        callbacks = {}
        identities = {}
        ready = asyncio.Event()
        stop = asyncio.Event()
        expiry = time.time_ns()//1000000 + 60000
        markets = [dict(market_key=d,slug='btc-updown-'+d+'-1000',token_ids={'UP':d+'u','DOWN':d+'d'},expiry_ts_ms=expiry,metadata={'conditionId':'0x'+c*64,'outcomes':['UP','DOWN']}) for d,c in [('5m','a'),('15m','b')]]
        class Books:
            def __init__(self,duration,tokens,on_quote,*args,identity,**kwargs):
                callbacks[duration]=on_quote;identities[duration]=identity
                if len(callbacks)==2:ready.set()
            async def run(self):await asyncio.Event().wait()
        class BTC:
            def __init__(self,symbol,on_tick,on_status):self.on_tick=on_tick
            async def run(self):
                try:await asyncio.Event().wait()
                finally:
                    # Cancellation of this sibling is delivered before market parents
                    # invalidate their children. Model a ready late callback.
                    if ready.is_set():
                        now=time.time_ns()//1000000
                        await callbacks['15m'](snapshot(identities['15m'],now))
                        await self.on_tick(MarketTick('binance','btcusdt',now,now,50000.0))
        async def trigger():
            await asyncio.wait_for(ready.wait(),1)
            if requested:stop.set()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.db'
            args=SimpleNamespace(db=path,seconds=.15,reconnect_after=0,compress_payloads=True,min_free_bytes=0,stop_event=stop,timestamp_contract='D5.1')
            with patch('app.d5.live.BinanceCollector',BTC),patch('app.d5.live.PolymarketOrderbookCollector',Books),patch('app.d5.live.PolymarketMarketDiscovery.get_active_btc_markets',return_value=markets):
                task=asyncio.create_task(trigger());result=await run(args);await task
            with closing(sqlite3.connect(path)) as db:
                marker=db.execute("SELECT event_id FROM events WHERE kind='COLLECTION_STOP'").fetchone()[0]
                late=db.execute("SELECT kind FROM events WHERE event_id>? AND kind IN ('BOOK','BTC')",(marker,)).fetchall()
                rejects=[decode(x[0]) for x in db.execute("SELECT payload_json FROM events WHERE kind='REJECT' AND event_id>?",(marker,))]
                self.assertEqual(late,[])
                self.assertEqual(sorted(x['feed'] for x in rejects if x.get('reason')=='COLLECTION_STOP_FENCE'),['15m','BTC'])
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(db.execute("SELECT count(*) FROM anchors WHERE status='OPEN'").fetchone()[0],0)
            self.assertEqual(result['status'],'STOPPED_BY_USER_CLEAN' if requested else 'STOPPED')
    async def test_requested_stop_fences_ready_sibling_callbacks(self):await self.exercise(True)
    async def test_timeout_fences_ready_sibling_callbacks(self):await self.exercise(False)
