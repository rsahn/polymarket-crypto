import pathlib,tempfile,unittest,json,hashlib
from unittest.mock import patch
import test_instrumented as fixtures
from tuned_review import run
import verify_source_provenance as provenance
class ProvenanceTests(unittest.TestCase):
 def test_hash_and_code_attestation_and_mismatch(self):
  for valid in (True,False):
   with self.subTest(valid=valid),tempfile.TemporaryDirectory() as t:
    root=pathlib.Path(t);source,sid=fixtures.InstrumentedTests().fixture(root);out=root/'review';run(source,out,sid,minimum=1);before=source.read_bytes()
    ref={'source':str(source),'source_bytes':source.stat().st_size,'source_mtime_ns':source.stat().st_mtime_ns,'source_sha256':hashlib.sha256(before).hexdigest() if valid else '0'*64};p=root/'reference.json';p.write_text(json.dumps(ref))
    with patch.object(provenance,'process_alive',return_value=False):result=provenance.verify(out,p)
    self.assertEqual('PASS' if valid else 'FAIL',result['status']);self.assertEqual(before,source.read_bytes())
    with patch.object(provenance,'process_alive',return_value=False):
     with self.assertRaises(FileExistsError):provenance.verify(out,p)
 def test_active_review_refuses_concurrent_hash(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);(root/'progress.json').write_text(json.dumps({'status':'RUNNING','pid':1}))
   with self.assertRaisesRegex(RuntimeError,'Wait for current review'):provenance.verify(root,root/'unused')
if __name__=='__main__':unittest.main()
