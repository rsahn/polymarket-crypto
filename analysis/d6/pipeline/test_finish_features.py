import unittest,tempfile,pathlib,contextlib,io,sys
from convert import convert
from finish_features import finish
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from app.d5.store import Store
from app.d5.observer import Observer
from test_d5 import identity,snapshot
class BlockFeatureTests(unittest.TestCase):
 def test_blocked_features_equal_reference(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);s=Store(root/'fixture.db',compress_payloads=True);m=identity();o=Observer(s);o.activate(m,1,0);o.observe(m,1,snapshot(m),{},1000)
   s.event('BTC',{'price':100.,'recv_ts_ms':1000,'event_ts_ms':1000},received_ts_ms=1000,event_ts_ms=1000,available_ts_ms=1000);s.event('SESSION_END',{'collection_seconds':1,'collection_stop_ts_ms':1000},received_ts_ms=2000,available_ts_ms=2000);s.close()
   with contextlib.redirect_stdout(io.StringIO()):convert(root/'fixture.db',root/'data',batch_size=2)
   finish(root/'data',root/'final',block=1)
   self.assertTrue(pq.read_table(root/'data/parquet/book_features.parquet').equals(pq.read_table(root/'final/parquet/book_features.parquet')))
if __name__=='__main__':unittest.main()
