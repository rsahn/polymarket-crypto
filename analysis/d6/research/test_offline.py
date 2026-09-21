import unittest,tempfile,pathlib,json,hashlib
from unittest.mock import patch
import offline
from offline import pa,pq
class OfflineTests(unittest.TestCase):
 def test_deterministic_stream_and_locked_oos(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);data=root/'data';p=data/'parquet';p.mkdir(parents=True)
   identity={'condition_id':'c','market_slug':'train','market_duration':'5m','token_up':'u','token_down':'d'}
   plan={'markets':[{**identity,'expiry_ts_ms':10000,'start_ms':1000,'split':'TRAIN'},{**identity,'condition_id':'o','market_slug':'oos','split':'OOS_LOCKED','expiry_ts_ms':20000,'start_ms':10000}]}
   lock=root/'SPLIT_LOCK.json';lock.write_text(json.dumps(plan));(root/'SPLIT_LOCK.sha256').write_text(hashlib.sha256(lock.read_bytes()).hexdigest());(data/'progress.json').write_text('{"status":"COMPLETE"}')
   def event(eid,kind,ts,**fields):return {'event_id':eid,'session_id':'fixture','kind':kind,'event_ts_ms':ts,'received_ts_ms':ts,'available_ts_ms':ts,**identity,'generation':1,'payload_json':None,**fields}
   events=[event(1,'ACTIVATE',0)];sides=[];btc=[];eid=2
   for ts in range(500,9500,500):
    events.append(event(eid,'BTC',ts));btc.append({'event_id':eid,'event_ts_ms':ts,'received_ts_ms':ts,'available_ts_ms':ts,'price':100+ts/10000});eid+=1
    events.append(event(eid,'BOOK',ts))
    for side,token,bid,ask in [('UP','u',.4,.42),('DOWN','d',.55,.57)]:sides.append({'event_id':eid,'side':side,'token_id':token,'event_ts_ms':ts,'received_ts_ms':ts,'best_bid':bid,'best_ask':ask,'bids_json':json.dumps([[bid,30]]).encode(),'asks_json':json.dumps([[ask,30]]).encode()})
    eid+=1
   events.append(event(eid,'BOOK',15000,condition_id='o',market_slug='oos'))
   tables={'events':events,'markets':[{**identity,'expiry_ts_ms':10000}],'book_sides':sides,'book_features':[{'unused':1}],'btc':btc}
   for name,rows in tables.items():pq.write_table(pa.Table.from_pylist(rows),p/(name+'.parquet'))
   with patch.object(offline,'HERE',root):
    offline.execute(data,root/'run1');offline.execute(data,root/'run2')
   a=json.loads((root/'run1/OFFLINE_COMPARISON.json').read_text());b=json.loads((root/'run2/OFFLINE_COMPARISON.json').read_text())
   self.assertEqual(a['results'],b['results']);self.assertFalse(a['oos_opened'])
   self.assertEqual(a['results']['TRAIN']['WAIT_ONLY_250']['cash'],'500')
   self.assertNotIn('o',a['results']['TRAIN']['D6_250']['positions'])
   self.assertGreater(a['results']['TRAIN']['ALWAYS_CHEAPER_SIDE_250']['fills'],0)
   original_limits=offline.Limits
   with patch.object(offline,'HERE',root),patch.object(offline,'Limits',side_effect=lambda latency_ms:original_limits(latency_ms=latency_ms,max_drawdown='.01')):
    offline.execute(data,root/'risk',root/'run1/replay_books.parquet')
   risk=json.loads((root/'risk/OFFLINE_COMPARISON.json').read_text())['results']['TRAIN']['ALWAYS_CHEAPER_SIDE_250']
   self.assertIsNotNone(risk['risk_stop']);self.assertLessEqual(risk['orders'],1)
if __name__=='__main__':unittest.main()
