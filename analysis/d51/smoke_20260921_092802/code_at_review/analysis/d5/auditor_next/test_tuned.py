import unittest,tempfile,pathlib,json,sqlite3,hashlib
import test_instrumented as fixtures
from instrumented_review import run as previous
from tuned_review import run
from sqlite_tuning import connect_ro
from app.d5 import quality
from app.d5.store import code_version
class TunedTests(unittest.TestCase):
 def test_reference_full_equality_alert_does_not_interrupt(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);source,sid=fixtures.InstrumentedTests().fixture(root);before=source.read_bytes();dest=root/'reference';dest.mkdir()
   expected=quality.review(source,dest,sid,minimum_seconds=1,final_code_version=code_version())
   result=run(source,root/'tuned',sid,budget=-1,minimum=1)
   self.assertEqual(expected,result);self.assertEqual(before,source.read_bytes())
   self.assertTrue(json.loads((root/'tuned/progress.json').read_text())['one_hour_alert'])
 def test_resume_repeats_missing_checks_and_matches_reference(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);source,sid=fixtures.InstrumentedTests().fixture(root);before=source.read_bytes()
   expected=previous(source,root/'previous',sid,60,1)
   actual=run(source,root/'resumed',sid,minimum=1,reuse_review=root/'previous')
   self.assertEqual(expected,actual);self.assertEqual(before,source.read_bytes())
   for name in ('INTEGRITY_CHECK.json','FOREIGN_KEY_CHECK.json','REPLAY_1.json','REPLAY_2.json','CARRIED_AUDIT_PROVENANCE.json'):self.assertTrue((root/'resumed'/name).exists())
   manifest=root/'previous/RUN_MANIFEST.json';m=json.loads(manifest.read_text());m['source_stat_before'][0]+=1;manifest.write_text(json.dumps(m))
   with self.assertRaisesRegex(RuntimeError,'PROVENANCE_MISMATCH'):run(source,root/'rejected',sid,reuse_review=root/'previous')
 def test_cache_connection_read_only(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);source,sid=fixtures.InstrumentedTests().fixture(root);before=source.read_bytes();db=connect_ro(source.as_uri()+'?mode=ro')
   self.assertEqual(-131072,db.execute('PRAGMA cache_size').fetchone()[0])
   with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM events')
   db.close();self.assertEqual(before,source.read_bytes())
   with self.assertRaises(ValueError):connect_ro(source.as_uri()+'?mode=rw')
if __name__=='__main__':unittest.main()
