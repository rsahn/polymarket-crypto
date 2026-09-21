import unittest
from context_join import pick_btc,select_context,pa
from offline import duckdb
class JoinTests(unittest.TestCase):
 def test_btc_strict_bound_and_gap(self):
  ticks=[{'available_ts_ms':900,'received_ts_ms':900,'event_ts_ms':900,'price':100},{'available_ts_ms':950,'received_ts_ms':950,'event_ts_ms':1100,'price':999}]
  self.assertEqual(pick_btc(ticks,[900,950],1000,0)['price'],100)
  self.assertIsNone(pick_btc(ticks,[900,950],900,0));self.assertIsNone(pick_btc(ticks,[900,950],1000,925))
 def test_book_identity_generation_future_and_freshness(self):
  a={'action_id':1,'bound_ms':2000,'outcome':'Up','quantity':5.,'split':'TRAIN','condition_id':'c','market_slug':'m','market_duration':'5m','active_generation':2,'activation_ms':1000,'token_id':'u'}
  base={'event_id':10,'condition_id':'c','market_slug':'m','market_duration':'5m','generation':2,'expiry_ts_ms':3000,'token_up':'u','token_down':'d',**{k:1500 for k in ('event_ts_ms','received_ts_ms','available_ts_ms','up_source_ms','up_received_ms','down_source_ms','down_received_ms')}}
  variants=[base,{**base,'event_id':11,'available_ts_ms':1900,'down_source_ms':2001},{**base,'event_id':12,'available_ts_ms':1950,'generation':1},{**base,'event_id':13,'available_ts_ms':1990,'condition_id':'foreign'},{**base,'event_id':14,'available_ts_ms':1991,'up_received_ms':999}]
  c=duckdb.connect();c.register('book_features',pa.Table.from_pylist(variants));self.assertEqual([r['event_id'] for r in select_context(c,[a])],[10])
  self.assertEqual(select_context(c,[{**a,'token_id':'bad'}]),[])
  self.assertEqual(select_context(c,[{**a,'bound_ms':1500}]),[]);c.close()
if __name__=='__main__':unittest.main()
