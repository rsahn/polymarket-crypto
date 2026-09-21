import unittest,copy,os
from unittest.mock import patch
from engine import Engine,Limits,D,guard
ID={'condition_id':'c','market_slug':'btc-updown-5m-0','market_duration':'5m','token_up':'u','token_down':'d','expiry_ts_ms':300000}
def book(t=1000):
 return {**ID,'event_ts_ms':t,'received_ts_ms':t,'up':{'token_id':'u','event_ts_ms':t,'bid':.4,'ask':.42,'bids':[[.4,30]],'asks':[[.42,13],[.43,7]]},'down':{'token_id':'d','event_ts_ms':t,'bid':.55,'ask':.57,'bids':[[.55,30]],'asks':[[.57,30]]}}
class EngineTests(unittest.TestCase):
 def test_no_live(self):
  for config in ({'LIVE_TRADING':'true'},{'MODE':'LIVE'},{'SEND_REAL_ORDERS':'yes'}):
   with self.assertRaises(RuntimeError):guard(config)
 def setup_engine(self,latency=0):
  e=Engine(Limits(latency_ms=latency));e.observe(ID,book(),1000);return e
 def test_latency(self):
  e=self.setup_engine(250);e.submit('c',{'action':'BUY_UP','reason':'test'},1000);e.execute_due(1249);self.assertEqual(len(e.fills),0);e.execute_due(1250);self.assertEqual(len(e.fills),1)
 def test_depth_and_no_double_fill(self):
  e=self.setup_engine();e.limits=Limits(latency_ms=0,max_order_qty='30',max_directional_shares='100')
  e.submit('c',{'action':'BUY_UP','reason':'test'},1000,20);e.execute_due(1000)
  self.assertEqual([f['qty'] for f in e.fills],[D(13),D(7)]);self.assertEqual(e.orders[-1]['vwap'],D('0.4235'))
  e.observe(ID,book(),1000);e.submit('c',{'action':'BUY_UP','reason':'test'},1000,20);e.execute_due(1000);self.assertEqual(len(e.fills),2)
 def test_source_future_excluded(self):
  e=self.setup_engine();b=book();b['up']['event_ts_ms']=1001;e.observe(ID,b,1000);self.assertFalse(e.admissible('c',1000))
 def test_append_future_btc_invariance(self):
  e=self.setup_engine();e.tick(100,0,0,0);e.tick(101,1000,1000,1000);a=e.features('c',1000);e.tick(1000,1500,1500,1500);self.assertEqual(a,e.features('c',1000))
 def test_cash_reserve(self):
  e=self.setup_engine();e.cash=D(100);self.assertIsNone(e.submit('c',{'action':'BUY_UP','reason':'test'},1000));self.assertEqual(e.cash,100)
 def test_sell_cannot_short(self):
  e=self.setup_engine();self.assertIsNone(e.submit('c',{'action':'REDUCE_UP','reason':'test'},1000));self.assertEqual(e.cash,500)
 def test_expiry_not_settlement(self):
  e=self.setup_engine();e.submit('c',{'action':'BUY_UP','reason':'test'},1000);e.execute_due(1000);cash=e.cash;e.state(300001);self.assertEqual(cash,e.cash);self.assertEqual(e.positions['c'].up,5)
 def test_settlement_verified_once(self):
  e=self.setup_engine();e.submit('c',{'action':'BUY_UP','reason':'test'},1000);e.execute_due(1000)
  with self.assertRaises(ValueError):e.settle('c','UP',300001,{'resolved':False,'condition_id':'c'})
  cash=e.cash;e.settle('c','UP',300001,{'resolved':True,'condition_id':'c'});self.assertEqual(e.cash,cash+5)
  with self.assertRaises(ValueError):e.settle('c','UP',300002,{'resolved':True,'condition_id':'c'})
 def test_cross_market(self):
  e=self.setup_engine();b=book();b['down']['token_id']='foreign'
  with self.assertRaises(ValueError):e.observe(ID,b,1000)
 def test_partial_and_fee_conservation(self):
  e=self.setup_engine();b=book();b['up']['asks']=[[.42,2]];e.observe(ID,b,1000);before=e.cash;e.submit('c',{'action':'BUY_UP','reason':'test'},1000);e.execute_due(1000)
  self.assertEqual(e.orders[-1]['status'],'PARTIAL');self.assertEqual(before-e.cash,e.positions['c'].up_cost);self.assertEqual(e.positions['c'].up,2)
if __name__=='__main__':unittest.main()
