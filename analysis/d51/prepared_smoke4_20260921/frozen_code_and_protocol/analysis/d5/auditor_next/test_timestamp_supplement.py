import unittest,sqlite3
from timestamp_supplement import scan
from app.d5.quality import feed_gaps
class TimestampTests(unittest.TestCase):
 def row(self,eid,ts,gen=1,side='UP',received=None):
  return (eid,'BOOK','5m','slug','cond',gen,ts,ts if received is None else received,eid*10000,side,side,ts,ts)
 def test_regression_and_generation(self):
  rows=[self.row(1,100),self.row(1,100,side='DOWN'),self.row(2,90),self.row(2,90,side='DOWN'),self.row(3,95),self.row(4,50,gen=2)]
  r=scan(rows);self.assertEqual(1,r['timestamp_checks']['BOOK_SOURCE']['previous_regressions']);self.assertEqual(2,r['timestamp_checks']['BOOK_SOURCE']['below_high_water']);self.assertEqual(2,r['timestamp_checks']['BOOK_SIDE_SOURCE']['previous_regressions']);self.assertEqual(4,r['accepted_events'])
 def test_feed_gaps_equal_reference_and_missing(self):
  rows=[self.row(1,None,received=1000),self.row(1,None,side='DOWN',received=1000),self.row(2,8000),self.row(3,7500)]
  r=scan(rows);self.assertEqual(1,r['timestamp_checks']['BOOK_SOURCE']['missing']);db=sqlite3.connect(':memory:')
  db.execute('CREATE TABLE events(session_id,kind,market_duration,received_ts_ms,event_id)')
  db.executemany('INSERT INTO events VALUES(?,?,?,?,?)',[('s','BOOK','5m',t,i) for i,t in ((1,1000),(2,8000),(3,7500))])
  expected=feed_gaps(db,'s',0,9000);db.close()
  for x in r['feed_gaps'].values():x.update(coverage_seconds=(x['last_ms']-x['first_ms'])/1000,initial_gap_ms=x['first_ms'],trailing_gap_ms=9000-x['last_ms'])
  self.assertEqual(expected,r['feed_gaps'])
 def test_original_sql_on_closed_fixture(self):
  import tempfile,pathlib
  import test_instrumented as fixtures
  from timestamp_supplement import QUERY
  with tempfile.TemporaryDirectory() as t:
   source,sid=fixtures.InstrumentedTests().fixture(pathlib.Path(t));before=source.read_bytes();db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
   result=scan(db.execute(QUERY,(sid,)));expected=feed_gaps(db,sid,0,10000);db.close()
   for x in result['feed_gaps'].values():x.update(coverage_seconds=(x['last_ms']-x['first_ms'])/1000,initial_gap_ms=max(0,x['first_ms']),trailing_gap_ms=max(0,10000-x['last_ms']))
   self.assertEqual(expected,result['feed_gaps']);self.assertEqual(4,result['accepted_events']);self.assertEqual(7,result['joined_rows']);self.assertEqual(before,source.read_bytes())
if __name__=='__main__':unittest.main()
