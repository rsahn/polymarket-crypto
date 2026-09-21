import unittest,tempfile,pathlib,json
from unittest.mock import patch
from test_engine import ID,book
from engine import Engine,Limits,D
import runtime
class SafetyTests(unittest.TestCase):
 def test_wire_cross_market_reject_is_critical(self):
  with self.assertRaisesRegex(ValueError,'CROSS_MARKET'):runtime.accept_snapshot({'reject_reason':'CROSS_MARKET_REJECT'})
  self.assertFalse(runtime.accept_snapshot({'reject_reason':'OUT_OF_ORDER'}))
 def test_gate_refuses_pending_verdict(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t);(p/'OFFLINE_VERDICT.json').write_text(json.dumps({'verdict':'WAITING_FOR_D5_AUDIT'}))
   with patch.object(runtime,'D6',p),self.assertRaisesRegex(RuntimeError,'NOT_PAPER_READY'):runtime.start_gate()
 def test_gate_requires_actual_quality(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t);(p/'OFFLINE_VERDICT.json').write_text(json.dumps({'verdict':'EXPERIMENTAL_PAPER_READY','technical_tests_passed':True,'critical_anomalies':[]}))
   with patch.object(runtime,'D6',p),patch.object(runtime,'ROOT',p),self.assertRaisesRegex(RuntimeError,'WAITING_FOR_D5_AUDIT'):runtime.start_gate()
 def test_expiry_pending_cannot_fill(self):
  e=Engine(Limits(latency_ms=300000));e.observe(ID,book(),1000);e.submit('c',{'action':'BUY_UP','reason':'fixture'},1000);e.execute_due(301000);self.assertEqual(e.orders[-1]['status'],'NO_FILL');self.assertEqual(e.cash,D(500))
 def test_reconnect_does_not_reset_liquidity(self):
  e=Engine(Limits(latency_ms=0));b=book();b['up']['asks']=[[.42,5]];e.observe(ID,b,1000)
  for n in range(2):
   e.submit('c',{'action':'BUY_UP','reason':'fixture'},1000);e.execute_due(1000);e.books.clear();e.observe(ID,b,1000)
  self.assertEqual(e.positions['c'].up,D(5))
 def test_risk_caps(self):
  e=Engine(Limits(latency_ms=0,max_directional_shares='3'));e.observe(ID,book(),1000);e.submit('c',{'action':'BUY_UP','reason':'fixture'},1000);e.execute_due(1000);self.assertEqual(e.positions['c'].up,D(3))
 def test_negative_inventory_detected(self):
  e=Engine();e.observe(ID,book(),1000);e.positions['c'].up=D(-1)
  with self.assertRaisesRegex(RuntimeError,'ACCOUNTING_INVARIANT'):e.state(1000)
 def test_metrics_time_and_settlement(self):
  e=Engine(Limits(latency_ms=0));e.observe(ID,book(),1000);e.submit('c',{'action':'BUY_UP','reason':'fixture'},1000);e.execute_due(1000)
  a=e.state(2000)['performance'];self.assertEqual(a['time_unhedged_seconds'],1);self.assertEqual(a['markets_traded'],1)
  e.state(2000);self.assertEqual(e.time_unhedged_ms,1000)
 def test_windows_status_retry(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'status.json';original=pathlib.Path.replace;attempts=[]
   def flaky(src,dst):
    attempts.append(1)
    if len(attempts)<3:raise PermissionError('Sharing violation')
    return original(src,dst)
   with patch.object(pathlib.Path,'replace',flaky):runtime.write_status(p,{'status':'RUNNING'})
   self.assertEqual(json.loads(p.read_text())['status'],'RUNNING');self.assertEqual(len(attempts),3)
if __name__=='__main__':unittest.main()

