import unittest,tempfile,pathlib,json
from unittest.mock import patch
from atomic_status import write_status,detail_mapping
class StatusTests(unittest.TestCase):
 def test_transient_reader_lock_retries_then_publishes_complete_json(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'state.json';p.write_text('{"old": true}');original=pathlib.Path.replace;calls=[]
   def locked(src,dst):
    calls.append(1)
    if len(calls)<3:
     self.assertEqual({'old':True},json.loads(p.read_text()))
     raise PermissionError('reader lock')
    return original(src,dst)
   with patch.object(pathlib.Path,'replace',locked),patch('atomic_status.time.sleep'):write_status(p,{'new':True})
   self.assertEqual(3,len(calls));self.assertEqual({'new':True},json.loads(p.read_text()))
 def test_persistent_error_preserves_previous_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'state.json';p.write_text('{"old": true}')
   with patch.object(pathlib.Path,'replace',side_effect=PermissionError('locked')) as replace,patch('atomic_status.time.sleep'):
    with self.assertRaises(PermissionError):write_status(p,{'new':True})
   self.assertEqual(30,replace.call_count);self.assertEqual({'old':True},json.loads(p.read_text()));self.assertEqual({'new':True},json.loads(p.with_suffix('.tmp').read_text()))
 def test_integrity_and_fk_details_are_not_carried_step_mappings(self):
  for value in ([['ok']],[],None):self.assertEqual({},detail_mapping(value))
  carried={'carried_forward_completed_step':True};self.assertIs(carried,detail_mapping(carried))
if __name__=='__main__':unittest.main()
