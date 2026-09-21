import unittest,sys,pathlib,tempfile,hashlib,json,io,contextlib
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from convert import convert
from app.d5.store import Store
from app.d5.observer import Observer
from test_d5 import identity,snapshot
class ConversionTests(unittest.TestCase):
 def check(self,version):
  with tempfile.TemporaryDirectory() as tmp:
   folder=pathlib.Path(tmp);source=folder/'fixture.db';s=Store(source,compress_payloads=version==2);m=identity();o=Observer(s);o.activate(m,1,0);o.observe(m,1,snapshot(m),{},1000)
   s.event('BTC',{'price':100.,'recv_ts_ms':1000,'event_ts_ms':1000},received_ts_ms=1000,event_ts_ms=1000,available_ts_ms=1000)
   s.event('SESSION_END',{'collection_seconds':1,'collection_stop_ts_ms':1000},received_ts_ms=2000,available_ts_ms=2000);s.close()
   before=hashlib.sha256(source.read_bytes()).hexdigest()
   with contextlib.redirect_stdout(io.StringIO()):convert(source,folder/'out',batch_size=2)
   self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest())
   report=json.loads((folder/'out/conversion_report.json').read_text());self.assertEqual(report['essential_checks']['feature_rows'],1)
   self.assertEqual(report['tables']['events']['rows'],4);self.assertEqual(report['source_sha256'],before)
 def test_resume_from_parquet_prefix(self):
  import pyarrow.parquet as pq
  with tempfile.TemporaryDirectory() as tmp:
   folder=pathlib.Path(tmp);source=folder/'fixture.db';s=Store(source,compress_payloads=True);m=identity();o=Observer(s);o.activate(m,1,0);o.observe(m,1,snapshot(m),{},1000)
   s.event('BTC',{'price':100.,'recv_ts_ms':1000,'event_ts_ms':1000},received_ts_ms=1000,event_ts_ms=1000,available_ts_ms=1000)
   s.event('SESSION_END',{'collection_seconds':1,'collection_stop_ts_ms':1000},received_ts_ms=2000,available_ts_ms=2000);s.close()
   with contextlib.redirect_stdout(io.StringIO()):convert(source,folder/'first',batch_size=2)
   event_path=folder/'first/parquet/events.parquet';table=pq.read_table(event_path);pq.write_table(table.slice(0,2),event_path)
   with contextlib.redirect_stdout(io.StringIO()):convert(source,folder/'resume',batch_size=2,resume_from=folder/'first')
   self.assertTrue(table.equals(pq.read_table(folder/'resume/parquet/events.parquet')))
   self.assertEqual(pq.ParquetFile(event_path).metadata.num_rows,2)
 def test_schema1(self):self.check(1)
 def test_schema2(self):self.check(2)
if __name__=='__main__':unittest.main()
