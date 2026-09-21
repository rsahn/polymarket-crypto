import asyncio,sqlite3,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import closing
from app.d5.live import run

class StopTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self,cleanup_error=False):
        class Waiting:
            async def run(self):
                try: await asyncio.Event().wait()
                finally:
                    if cleanup_error: raise RuntimeError('cleanup failed')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'new.db'; stop=asyncio.Event()
            args=SimpleNamespace(db=path,seconds=1,reconnect_after=0,compress_payloads=True,min_free_bytes=0,stop_event=stop,timestamp_contract='D5.1')
            async def request(): await asyncio.sleep(.03);stop.set()
            with patch('app.d5.live.BinanceCollector',return_value=Waiting()),patch('app.d5.live.PolymarketMarketDiscovery.get_active_btc_markets',return_value=[]):
                requester=asyncio.create_task(request());result=await run(args);await requester
            with closing(sqlite3.connect(path)) as db:
                status=db.execute('SELECT status FROM sessions').fetchone()[0]
                self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='COLLECTION_STOP'").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='SESSION_END'").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT count(*) FROM anchors WHERE status='OPEN'").fetchone()[0],0)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(result['status'],status)
            return status
    async def test_requested_stop_is_distinct_and_committed(self):
        self.assertEqual(await self.execute(),'STOPPED_BY_USER_CLEAN')
    async def test_cleanup_error_never_clean(self):
        self.assertEqual(await self.execute(True),'FAILED')
