import unittest,tempfile,pathlib,json,asyncio
from unittest.mock import patch
import runtime
class IdleFeed:
 def __init__(self,*args,**kwargs):pass
 async def run(self):await asyncio.Event().wait()
class FailedFeed(IdleFeed):
 async def run(self):raise ValueError('CROSS_MARKET_TEST_FIXTURE')
class RuntimeTests(unittest.IsolatedAsyncioTestCase):
 async def run_fixture(self,feed,fails):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);out=root/'session'
   with patch.object(runtime.clock_guard,'check',return_value={'passed':True,'fixture':True}),patch.object(runtime,'D6',root),patch.object(runtime,'start_gate',return_value={'fixture':True}),patch.object(runtime,'BinanceCollector',feed),patch.object(runtime.PolymarketMarketDiscovery,'get_active_btc_markets',return_value=[]):
    if fails:
     with self.assertRaisesRegex(ValueError,'CROSS_MARKET'):await runtime.run(out,.15)
    else:await runtime.run(out,.15)
   report=json.loads((out/'PAPER_24H_REPORT.json').read_text());self.assertFalse(report['completed_24h']);self.assertEqual(report['account']['cash'],'500');self.assertEqual(report['account']['orders'],0);self.assertTrue(report['strategy_hash_unchanged'])
   self.assertEqual(report['status'],'FAILED' if fails else 'COMPLETED')
   import sqlite3
   c=sqlite3.connect(out/'paper.db');self.assertEqual(c.execute('SELECT status FROM session').fetchone()[0],report['status']);self.assertEqual(c.execute('SELECT kind FROM journal ORDER BY sequence DESC LIMIT 1').fetchone()[0],'SESSION_END');c.close()
 async def test_short_fixture_not_24h_validation(self):await self.run_fixture(IdleFeed,False)
 async def test_critical_feed_failure_closes_and_reports(self):await self.run_fixture(FailedFeed,True)
if __name__=='__main__':unittest.main()
