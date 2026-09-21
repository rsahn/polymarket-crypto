import unittest,tempfile,pathlib,sys,json
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis/d5/auditor_next'))
import test_instrumented as fixtures
from run_smoke import review

class Review51Tests(unittest.TestCase):
    def test_full_chain_preserves_source_and_fails_missing_new_contract(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);source,sid=fixtures.InstrumentedTests().fixture(root);before=source.read_bytes()
            result=review(source,root/'review',sid,[],minimum=1)
            self.assertEqual(before,source.read_bytes())
            self.assertEqual(result['D51_DATA_QUALITY'],'FAIL')
            self.assertIn('WRONG_TEMPORAL_CONTRACT',result['failures'])
            self.assertIn('NTP_SEQUENCE_INCOMPLETE',result['failures'])
            for n in ('INTEGRITY_CHECK.json','FOREIGN_KEY_CHECK.json','REPLAY_1.json','REPLAY_2.json','D51_SUPPLEMENT.json'):
                self.assertTrue((root/'review'/n).exists())
            a=json.loads((root/'review/REPLAY_1.json').read_text());b=json.loads((root/'review/REPLAY_2.json').read_text())
            self.assertEqual(a['result'],b['result']);self.assertEqual(a['decision_sha256'],b['decision_sha256'])
