import pathlib,sys,tempfile,unittest,json,sqlite3
from dataclasses import replace
from test_acceleration import ROOT,identity,snapshot,Store,Observer
from app.d5 import quality
from app.d5.store import code_version
from instrumented_review import run
class InstrumentedTests(unittest.TestCase):
 def fixture(self,root):
  p=root/'source.db';s=Store(p,compress_payloads=True);o=Observer(s)
  for i,m in enumerate((identity('A'),identity('B'),replace(identity('C'),market_duration='15m'))):
   t=(i+1)*1000;o.activate(m,1,t);o.observe(m,1,snapshot(m,t),{},t)
  s.event('BTC',{'price':100.,'recv_ts_ms':4000,'event_ts_ms':4000},received_ts_ms=4000,event_ts_ms=4000,available_ts_ms=4000)
  s.event('SESSION_END',{'collection_seconds':4,'collection_stop_ts_ms':4000},received_ts_ms=5000,available_ts_ms=5000)
  sid=s.session_id;s.close('FAILED');return p,sid
 def test_full_equivalence_and_source_unchanged(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);p,sid=self.fixture(root);before=p.read_bytes();old=root/'reference';old.mkdir()
   expected=quality.review(p,old,sid,minimum_seconds=1,final_code_version=code_version())
   actual=run(p,root/'new',sid,60,1)
   self.assertEqual(expected,actual);self.assertEqual(before,p.read_bytes())
   status=json.loads((root/'new/progress.json').read_text(encoding='utf-8'))
   self.assertEqual(8,len(status['completed_steps']));self.assertEqual('FAIL',status['D5_DATA_QUALITY'])
   self.assertTrue(actual['REPLAY_HASHES_EQUAL']);self.assertIn('UNCLEAN_STOP',actual['QUALITY_FAILURES'])
 def test_audit_failure_stops_and_retains(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);p,sid=self.fixture(root)
   with sqlite3.connect(p) as db:db.execute("UPDATE events SET token_up='' WHERE kind='BOOK'")
   db.close()
   before=p.read_bytes()
   with self.assertRaisesRegex(RuntimeError,'AUDIT_NEXT_FAILED'):run(p,root/'new',sid,60,1)
   self.assertTrue((root/'new/AUDIT_NEXT_REPORT.json').exists());self.assertFalse((root/'new/REPLAY_1.json').exists());self.assertEqual(before,p.read_bytes())
 def test_foreign_key_failure_stops_before_replays(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);p,sid=self.fixture(root);db=sqlite3.connect(p)
   db.execute("INSERT INTO events(session_id,kind,event_ts_ms,received_ts_ms,available_ts_ms,payload_json) VALUES('orphan','BTC',1,1,1,'{}')");db.commit();db.close();before=p.read_bytes()
   with self.assertRaisesRegex(RuntimeError,'SOURCE_SQLITE_CHECK_FAILED'):run(p,root/'new',sid,60,1)
   self.assertTrue((root/'new/FOREIGN_KEY_CHECK.json').exists());self.assertFalse((root/'new/REPLAY_1.json').exists());self.assertEqual(before,p.read_bytes())
 def test_timeout_fails_closed(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);p,sid=self.fixture(root)
   with self.assertRaises(TimeoutError):run(p,root/'new',sid,-1,1)
   self.assertEqual('FAIL',json.loads((root/'new/VERDICT.json').read_text())['D5_DATA_QUALITY'])
if __name__=='__main__':unittest.main()
