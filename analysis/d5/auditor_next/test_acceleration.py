import tempfile,pathlib,json,hashlib,sys,unittest,types
import test_audit_next as fixtures
from test_audit_next import reference,ROOT
from acceleration import build_projection,replay_database
from audit_next import audit
from app.d5 import quality,replay
from app.d5.store import Store
from app.d5.observer import Observer
sys.path.insert(0,str(ROOT/'backend/tests'))
from test_d5 import identity,snapshot
class AccelerationTests(unittest.TestCase):
 def test_projection_equivalence(self):
  for version in (1,2):
   for corrupt in (False,True):
    with self.subTest(version=version,corrupt=corrupt),tempfile.TemporaryDirectory() as tmp:
     p=pathlib.Path(tmp)/'source.db';out=pathlib.Path(tmp)/'projection.db'
     fixtures.Equivalence().fixture(p,version,2000,corrupt)
     before=p.read_bytes();updates=[];build_projection(p,out,updates.append,batch_size=31)
     self.assertEqual(reference(p,'s'),audit(out,'s'));self.assertEqual(before,p.read_bytes())
     self.assertTrue(any(r.get('rows',0)>31 for r in updates))
 def test_whole_chain_accelerated(self):
  for compressed in (False,True):
   with self.subTest(compressed=compressed),tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp);p=root/'source.db';s=Store(p,compress_payloads=compressed)
    o=Observer(s);m=identity();o.activate(m,1,0)
    for t in (1000,2000,8000):o.observe(m,1,snapshot(m,t),{},t)
    s.event('SESSION_END',{'collection_seconds':8,'collection_stop_ts_ms':8000},received_ts_ms=9000,available_ts_ms=9000)
    sid=s.session_id;s.close('FAILED');before=p.read_bytes()
    original=root/'old';original.mkdir();expected=quality.review(p,original,sid,minimum_seconds=1)
    projected=root/'projection.db';build_projection(p,projected)
    namespace=dict(quality.review.__globals__)
    namespace.update(audit=lambda source,session:audit(projected,session),replay_database=replay_database)
    candidate=types.FunctionType(quality.review.__code__,namespace,'review',quality.review.__defaults__)
    candidate.__kwdefaults__=quality.review.__kwdefaults__.copy()
    dest=root/'new';dest.mkdir();actual=candidate(p,dest,sid,minimum_seconds=1)
    self.assertEqual(expected,actual);self.assertEqual(before,p.read_bytes())
    for name in ('REPLAY_1.json','REPLAY_2.json'):
     self.assertEqual(json.loads((original/name).read_text()),json.loads((dest/name).read_text()))
 def test_other_strategies_preserve_context(self):
  class NeedContext(replay.NoTrade):
   def on_event(self,context):
    assert context['kind']=='CLOCK'
    return super().on_event(context)
  from acceleration import FastNoTradeReplay
  event={'event_id':1,'available_ts_ms':1000,'kind':'CLOCK','payload':{}}
  a=replay.Replay(NeedContext());b=FastNoTradeReplay(NeedContext())
  a.process(event);b.process(event);self.assertEqual(a.results(),b.results())
if __name__=='__main__':unittest.main()
