import json,sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from app.d5.writer_core import WriterCore
from app.d5.identity import MarketIdentity
from app.d5.store import decode

class WriterCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'new.db';self.now=1000
        self.core=WriterCore(self.path,clock=lambda:self.now)
        self.identity=MarketIdentity('5m','btc-updown-5m-1','condition-a','u','d',10000)
    def tearDown(self):
        if not self.core.closed:self.core.fail('test cleanup')
        self.tmp.cleanup()
    def send(self,kind,received=1000,**kw):
        return self.core.apply(dict(sequence=self.core.next_sequence,kind=kind,received_ts_ms=received,**kw))
    def activate(self,generation=1):
        self.send('ACTIVATE',identity=self.identity,generation=generation)
    def snapshot(self,received=1001):
        return {**self.identity.fields(),'timestamp_contract':'D5.1','wire_event_ts_ms':999,
                'event_ts_ms':999,'received_ts_ms':received,'wire_hash':'unique-'+str(received),
                **{side:{'token_id':token,'bid':.4,'ask':.6,'bid_qty':2.,'ask_qty':3.,
                         'bids':[(.4,2.)],'asks':[(.6,3.)],'event_ts_ms':999,'received_ts_ms':received}
                   for side,token in (('up','u'),('down','d'))}}
    def rows(self,query):
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:return db.execute(query).fetchall()
    def test_receipt_preserved_processing_time_and_commit_ack(self):
        self.activate();self.now=1400
        ack=self.send('BOOK',received=1001,identity=self.identity,generation=1,snapshot=self.snapshot())
        self.assertEqual(ack['processed_at_ms'],1400);self.assertEqual(ack['committed_sequence'],-1)
        flush=self.send('FLUSH');self.assertEqual(flush['committed_sequence'],2)
        self.assertEqual(self.rows("SELECT received_ts_ms,available_ts_ms FROM events WHERE kind='BOOK'"),[(1001,1400)])
        self.send('STOP');self.assertTrue(self.core.closed)
        self.assertEqual(self.rows("SELECT count(*) FROM anchors WHERE status='OPEN'"),[(0,)])
        self.assertEqual(self.rows('PRAGMA integrity_check'),[('ok',)])
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])
        with self.assertRaises(RuntimeError):self.send('BOOK')
    def test_queued_old_generation_is_rejected(self):
        self.activate();self.send('INVALIDATE',identity=self.identity,generation=1,reason='RECONNECT')
        self.activate(2);self.send('BOOK',received=1001,identity=self.identity,generation=1,snapshot=self.snapshot())
        self.send('STOP')
        r=self.rows("SELECT payload_json FROM events WHERE kind='REJECT'")
        self.assertEqual(decode(r[0][0])['reason'],'CROSS_MARKET_REJECT')
    def test_backlog_past_expiry_preserves_rejection(self):
        self.activate();self.now=10001
        self.send('BOOK',received=1001,identity=self.identity,generation=1,snapshot=self.snapshot());self.send('STOP')
        self.assertEqual(self.rows("SELECT count(*) FROM events WHERE kind='BOOK'"),[(0,)])
        p=decode(self.rows("SELECT payload_json FROM events WHERE kind='REJECT'")[0][0])
        self.assertEqual(p['reason'],'POST_EXPIRY_REJECT');self.assertEqual(p['snapshot']['received_ts_ms'],1001)
    def test_future_btc_source_not_used_in_anchor(self):
        self.activate();self.now=1500
        self.send('BTC',received=1100,tick={'price':50000.,'recv_ts_ms':1100,'event_ts_ms':9000})
        self.send('BOOK',received=1200,identity=self.identity,generation=1,snapshot=self.snapshot(1200));self.send('STOP')
        for row in self.rows('SELECT features_json FROM anchors'):
            self.assertIsNone(decode(row[0])['btc']['btc_price'])
    def test_sequence_error_is_terminal_failed(self):
        with self.assertRaises(ValueError):self.core.apply(dict(sequence=2,kind='FLUSH',received_ts_ms=1000))
        self.assertTrue(self.core.failed);self.assertTrue(self.core.closed)
        self.assertEqual(self.rows('SELECT status FROM sessions'),[('FAILED',)])
        with self.assertRaises(RuntimeError):self.send('STOP')
    def test_flush_failure_never_acknowledged_as_committed(self):
        self.activate()
        with patch.object(self.core.store,'flush',side_effect=OSError('synthetic commit fault')):
            with self.assertRaises(OSError):self.send('FLUSH')
        self.assertEqual(self.core.committed_sequence,-1)
        self.assertTrue(self.core.failed)
        self.assertEqual(self.rows('SELECT status FROM sessions'),[('FAILED',)])
    def test_invalid_stop_cannot_become_clean(self):
        with self.assertRaises(ValueError):self.send('STOP',status='PASS')
        self.assertEqual(self.rows('SELECT status FROM sessions'),[('FAILED',)])
    def test_expiry_then_matching_invalidate_is_idempotent(self):
        self.activate();self.now=10001;self.send('EXPIRE')
        self.send('INVALIDATE',identity=self.identity,generation=1,reason='EXPIRE');self.send('STOP')
        self.assertEqual(self.rows("SELECT count(*) FROM events WHERE kind='EXPIRE'"),[(1,)])
    def test_expiry_does_not_allow_wrong_generation_invalidate(self):
        self.activate();self.now=10001;self.send('EXPIRE')
        with self.assertRaises(ValueError):self.send('INVALIDATE',identity=self.identity,generation=2,reason='EXPIRE')
        self.assertTrue(self.core.failed)
    def test_failed_ingress_stop_preserves_failed_verdict(self):
        self.activate();self.send('STOP',status='FAILED',cleanup_errors=['queue overflow'])
        self.assertEqual(self.rows('SELECT status FROM sessions'),[('FAILED',)])
        self.assertEqual(self.rows("SELECT count(*) FROM anchors WHERE status='OPEN'"),[(0,)])
    def test_existing_database_never_reopened(self):
        with self.assertRaises(FileExistsError):WriterCore(self.path)
    def test_receipt_mismatch_fails(self):
        self.activate()
        with self.assertRaises(ValueError):self.send('BOOK',received=1002,identity=self.identity,generation=1,snapshot=self.snapshot())
        self.assertTrue(self.core.failed)
    def test_future_command_receipt_and_wall_regression_never_backdate(self):
        self.activate();self.now=500
        ack=self.send('EVENT',received=2000,event_kind='CLOCK_SAMPLE',payload={})
        self.assertEqual(ack['processed_at_ms'],2000)
        self.now=300;ack=self.send('STOP',received=1000)
        self.assertEqual(ack['processed_at_ms'],2000)

if __name__=='__main__':unittest.main()
