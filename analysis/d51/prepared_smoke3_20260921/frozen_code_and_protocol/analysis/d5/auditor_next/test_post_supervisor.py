import unittest,tempfile,pathlib,json,hashlib
from unittest.mock import patch
import test_instrumented as fixtures
from tuned_review import run
import post_review_supervisor as supervisor
import verify_source_provenance as provenance
import timestamp_supplement as supplement
class PostSupervisorTests(unittest.TestCase):
 def test_full_serial_synthetic_chain(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);source,sid=fixtures.InstrumentedTests().fixture(root);out=root/'review';core=run(source,out,sid,minimum=1);before=source.read_bytes()
   reference=root/'reference.json';reference.write_text(json.dumps({'source':str(source),'source_bytes':source.stat().st_size,'source_mtime_ns':source.stat().st_mtime_ns,'source_sha256':hashlib.sha256(before).hexdigest()}))
   with patch.object(supervisor,'process_alive',return_value=False),patch.object(provenance,'process_alive',return_value=False),patch.object(supplement,'process_alive',return_value=False):supervisor.main(out,reference)
   result=json.loads((out/'SUPERVISOR_D5_VERDICT.json').read_text());self.assertEqual('PASS',result['source_and_code_provenance']);self.assertTrue(all(result['replay_comparison'].values()));self.assertEqual(core['QUALITY_FAILURES'],result['core_quality_failures']);self.assertIn('UNCLEAN_STOP',result['quality_failures']);self.assertEqual('FAIL',result['D5_DATA_QUALITY']);self.assertEqual(before,source.read_bytes())
   self.assertEqual('COMPLETE',json.loads((out/'post_review_progress.json').read_text())['status'])
if __name__=='__main__':unittest.main()
