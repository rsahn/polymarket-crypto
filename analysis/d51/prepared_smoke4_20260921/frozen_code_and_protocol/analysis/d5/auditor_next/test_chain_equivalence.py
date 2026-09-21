"""Whole-chain equivalence on disposable fixtures only; no production access."""
import copy,hashlib,json,pathlib,sys,tempfile,types,unittest
from test_audit_next import ROOT,audit
sys.path.insert(0,str(ROOT/'backend/tests'))
from app.d5 import quality
from app.d5.store import Store
from app.d5.observer import Observer
from test_d5 import identity,snapshot
class ChainEquivalence(unittest.TestCase):
 def compare(self,compressed=False,fault=None):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);p=root/'fixture.db';store=Store(p,compress_payloads=compressed)
   m=identity();o=Observer(store);o.activate(m,1,0)
   eid=o.observe(m,1,snapshot(m),{},1000)
   o.activate(m,2,2000);o.observe(m,2,snapshot(m,2000),{},2000)
   store.event('SESSION_END',{'elapsed_seconds':12,'collection_seconds':2,'collection_stop_ts_ms':3000},received_ts_ms=12000,available_ts_ms=12000)
   sid=store.session_id;store.close('FAILED' if fault=='failed' else 'STOPPED')
   import sqlite3
   db=sqlite3.connect(p)
   if fault=='open':db.execute("UPDATE anchors SET status='OPEN'")
   if fault=='foreign_key':db.execute("UPDATE book_sides SET event_id=event_id+999999 WHERE side='UP'")
   if fault=='expiry':db.execute("UPDATE book_sides SET received_ts_ms=999999 WHERE side='DOWN'")
   db.commit();db.close()
   before=hashlib.sha256(p.read_bytes()).hexdigest()
   original_globals=quality.review.__globals__
   alternate_globals=dict(original_globals);alternate_globals['audit']=audit
   candidate=types.FunctionType(quality.review.__code__,alternate_globals,quality.review.__name__,quality.review.__defaults__,quality.review.__closure__)
   candidate.__kwdefaults__=quality.review.__kwdefaults__.copy()
   outputs=[]
   for name,fn in [('old',quality.review),('new',candidate)]:
    out=root/name;out.mkdir();outputs.append(fn(p,out,sid,minimum_seconds=1,final_code_version='deliberate_mismatch'))
   self.assertEqual(outputs[0],outputs[1])
   for name in ('DATA_QUALITY_REPORT.json','REPLAY_1.json','REPLAY_2.json','FINAL_DATA_QUALITY_REPORT.json'):
    self.assertEqual(json.loads((root/'old'/name).read_text()),json.loads((root/'new'/name).read_text()))
   self.assertEqual(before,hashlib.sha256(p.read_bytes()).hexdigest())
   self.assertIs(quality.review.__globals__,original_globals)
   if fault=='failed':self.assertIn('UNCLEAN_STOP',outputs[1]['QUALITY_FAILURES'])
   if fault=='open':self.assertGreater(outputs[1]['OPEN_ANCHORS'],0)
   if fault=='foreign_key':self.assertTrue(outputs[1]['FOREIGN_KEY_VIOLATIONS'])
   if fault=='expiry':self.assertGreater(outputs[1]['POST_EXPIRY_ACCEPTED'],0)
   self.assertTrue(outputs[1]['REPLAY_HASHES_EQUAL']);self.assertTrue(outputs[1]['NO_TRADE_VERIFIED'])
 def test_chain_schema1(self):self.compare()
 def test_chain_schema2(self):self.compare(True)
 def test_preserve_failed(self):self.compare(True,'failed')
 def test_open_anchors(self):self.compare(True,'open')
 def test_foreign_keys(self):self.compare(True,'foreign_key')
 def test_expiry_sides(self):self.compare(True,'expiry')
 def test_gate_failure_matrix(self):
  base={'SMOKE_FAILURES':[],'SESSION':{'status':'STOPPED'},'ACTUAL_DURATION_SECONDS':10801,'SQLITE_INTEGRITY_CHECK':['ok'],'FOREIGN_KEY_VIOLATIONS':[],'OPEN_ANCHORS':0,'POST_EXPIRY_ACCEPTED':0,'FEED_GAPS':{n:{'coverage_seconds':10800,'gaps_over_5s':0,'initial_gap_ms':0,'trailing_gap_ms':0,'receive_regressions':0} for n in ('5m','15m','BTC')}}
  self.assertEqual(quality.quality_gate(base,True,10800),[])
  for key,value,failure in [('SQLITE_INTEGRITY_CHECK',['broken'],'SQLITE_INTEGRITY_FAILURE'),('FOREIGN_KEY_VIOLATIONS',[[1]],'SQLITE_INTEGRITY_FAILURE'),('OPEN_ANCHORS',1,'OPEN_ANCHORS'),('POST_EXPIRY_ACCEPTED',1,'POST_EXPIRY_ACCEPTED'),('ACTUAL_DURATION_SECONDS',0,'DURATION_BELOW_24H'),('CODE_CHANGED_DURING_COLLECTION',True,'CODE_PROVENANCE_CHANGED')]:
   r=copy.deepcopy(base);r[key]=value;self.assertIn(failure,quality.quality_gate(r,True,10800))
  for feed in ('5m','15m','BTC'):
   for key,value,prefix in [('coverage_seconds',1,'INSUFFICIENT_COVERAGE_'),('gaps_over_5s',1,'GAPS_REQUIRE_REVIEW_'),('initial_gap_ms',10001,'GAPS_REQUIRE_REVIEW_'),('trailing_gap_ms',10001,'GAPS_REQUIRE_REVIEW_'),('receive_regressions',1,'RECEIVE_CLOCK_REGRESSION_')]:
    r=copy.deepcopy(base);r['FEED_GAPS'][feed][key]=value;self.assertIn(prefix+feed,quality.quality_gate(r,True,10800))
  self.assertIn('REPLAY_FAILED_OR_DIFFERENT',quality.quality_gate(base,False,10800))
if __name__=='__main__':unittest.main()
