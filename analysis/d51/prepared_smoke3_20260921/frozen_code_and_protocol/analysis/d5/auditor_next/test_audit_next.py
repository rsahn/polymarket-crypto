import hashlib,importlib.util,json,pathlib,random,sqlite3,sys,tempfile,time,unittest,zlib
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from app.d5.audit import audit as reference
from audit_next import audit
class Equivalence(unittest.TestCase):
 def fixture(self,path,version=1,n=30,corrupt=False):
  db=sqlite3.connect(path)
  db.executescript((ROOT/f'backend/app/d5/{"schema.sql" if version==1 else "schema_v2.sql"}').read_text())
  db.execute("INSERT INTO sessions VALUES('s',0,900000,'fixture',?,'SHADOW','STOPPED','{}')",(version,))
  for i in range(3):
   db.execute('INSERT INTO markets VALUES(?,?,?,?,?,?,?)',(f'c{i}',f'm{i}','15m' if i==2 else '5m',f'u{i}',f'd{i}',900000,'{}'))
  rng=random.Random(40)
  for i in range(n):
   m=i%3;ts=i*1000+rng.randrange(-7000,7000)
   kind='BTC' if i%7==0 else 'REJECT' if i%11==0 else 'BOOK'
   payload=json.dumps({'reason':'OUT_OF_ORDER','padding':'a'*800}) if kind=='REJECT' else '{}'
   if version==2:payload=zlib.compress(payload.encode())
   eid=db.execute('INSERT INTO events(session_id,kind,event_ts_ms,received_ts_ms,available_ts_ms,market_duration,market_slug,condition_id,token_up,token_down,generation,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('s',kind,None if i%5==0 else ts,ts,ts,'15m' if m==2 else '5m',f'm{m}',f'c{m}',f'u{m}',f'd{m}',i%2,payload)).lastrowid
   if kind=='BOOK':
    for side,token in [('UP',f'u{m}'),('DOWN',f'd{m}')]:
     db.execute('INSERT INTO book_sides VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(eid,side,token,ts,ts,.4,.5,10,20,.1,'[]','[]','hash','seq'))
  if corrupt and n:
   # Corruption only in this disposable fixture, never the collected dataset.
   db.execute("UPDATE events SET token_up='',event_ts_ms=999999 WHERE kind='BOOK' AND event_id=(SELECT min(event_id) FROM events WHERE kind='BOOK')")
   db.execute("DELETE FROM book_sides WHERE side='UP' AND event_id=(SELECT min(event_id) FROM events WHERE kind='BOOK')")
   db.execute("UPDATE book_sides SET token_id='foreign',received_ts_ms=999999 WHERE side='DOWN'")
  db.commit();db.close()
 def check(self,version,n,corrupt):
  with tempfile.TemporaryDirectory() as tmp:
   path=pathlib.Path(tmp)/'synthetic.db';self.fixture(path,version,n,corrupt)
   before=hashlib.sha256(path.read_bytes()).hexdigest();events=[]
   expected=reference(path,'s');actual=audit(path,'s',events.append)
   self.assertEqual(expected,actual)
   self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
   ends=[e for e in events if e['stage']=='market_gaps_stream' and e['event']=='complete']
   self.assertEqual(ends[0]['rows_processed'],actual['ROWS'])
   self.assertTrue(all(e.get('percent') is None for e in events if e['event']=='heartbeat'))
 def test_v1_clean(self):self.check(1,100,False)
 def test_v2_clean(self):self.check(2,100,False)
 def test_v1_corrupt(self):self.check(1,100,True)
 def test_v2_corrupt(self):self.check(2,100,True)
 def test_empty(self):self.check(1,0,False)
 def test_single_book(self):self.check(1,2,False)
 def test_gaps_and_rotations(self):self.check(2,2000,True)
 def test_missing_session(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=pathlib.Path(tmp)/'synthetic.db';self.fixture(path)
   with self.assertRaisesRegex(ValueError,'Unknown session'):audit(path,'absent')
   path.unlink() # Also proves that exception cleanup releases its Windows handle.
if __name__=='__main__':unittest.main()
