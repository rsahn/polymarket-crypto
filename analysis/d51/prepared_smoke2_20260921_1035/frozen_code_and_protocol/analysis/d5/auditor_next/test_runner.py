import pathlib,tempfile,sys,unittest,json
from test_audit_next import ROOT
from test_d5 import identity,snapshot
from app.d5.store import Store
from app.d5.observer import Observer
from app.d5 import replay
from acceleration import FastNoTradeReplay
from run_accelerated import run
class RunnerTests(unittest.TestCase):
 def test_invalid_json_number_preserved(self):
  m=identity();book=snapshot(m);book['extra']=float('nan')
  event={'event_id':1,'available_ts_ms':1000,'kind':'BOOK','payload':book,'identity':m.fields()}
  for cls in (replay.Replay,FastNoTradeReplay):
   with self.assertRaises(ValueError):cls(replay.NoTrade()).process(event)
 def test_invalid_btc_timestamp_preserved(self):
  event={'event_id':1,'available_ts_ms':1000,'kind':'BTC','payload':{'price':100.,'recv_ts_ms':'bad','event_ts_ms':1000}}
  for cls in (replay.Replay,FastNoTradeReplay):
   with self.assertRaises(TypeError):cls(replay.NoTrade()).process(event)
 def fixture(self,root):
  p=root/'fixture.db';s=Store(p,compress_payloads=True);m=identity();o=Observer(s);o.activate(m,1,0);o.observe(m,1,snapshot(m),{},1000)
  sid=s.session_id;s.close('FAILED');return p,sid
 def test_runner_real_sql_and_both_replays(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);p,sid=self.fixture(root);before=p.read_bytes()
   result=run(p,root/'output',sid,60,1)
   self.assertTrue(result['REPLAY_HASHES_EQUAL']);self.assertEqual(['ok'],result['SQLITE_INTEGRITY_CHECK']);self.assertEqual(before,p.read_bytes())
   self.assertTrue((root/'output/REPLAY_2.json').exists())
 def test_budget_is_incomplete_not_pass(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);p,sid=self.fixture(root)
   with self.assertRaises(TimeoutError):run(p,root/'output',sid,-1,1)
   status=json.loads((root/'output/progress.json').read_text());self.assertEqual('INCOMPLETE_TIME_BUDGET',status['phase']);self.assertFalse(status['research_allowed'])
if __name__=='__main__':unittest.main()
