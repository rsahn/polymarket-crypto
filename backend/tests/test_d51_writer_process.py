import asyncio,tempfile,sqlite3,unittest
from contextlib import closing
from pathlib import Path
from app.d5.writer_process import ProcessWriter
from app.d5.store import decode

class WriterProcessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'fixture.db';self.writer=None
    async def asyncTearDown(self):
        if self.writer is not None:
            if self.writer.error is not None:await self.writer.release_failed()
            elif not self.writer.closed_ack:await self.writer.stop()
        self.tmp.cleanup()
    async def start(self,**kwargs):
        self.writer=ProcessWriter(self.path,**kwargs);await self.writer.start();return self.writer
    def tick(self):return {'kind':'BTC','received_ts_ms':1000,'tick':{'recv_ts_ms':1000,'event_ts_ms':999,'price':50000.}}
    def rows(self,sql):
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:return db.execute(sql).fetchall()
    async def test_default_transport_uses_large_batches_with_same_admission_bound(self):
        w=await self.start()
        self.assertEqual(w.batch_size,256);self.assertEqual(w.max_items,8192);self.assertEqual(w.max_bytes,64*1024*1024)
        await w.stop()
    async def test_batch_boundaries_and_drain(self):
        for n in (0,1,31,32,33):
            with self.subTest(n=n):
                self.path=Path(self.tmp.name)/('fixture'+str(n)+'.db')
                w=await self.start()
                for _ in range(n):w.submit(self.tick())
                ack=await w.stop();self.assertTrue(ack['closed']);self.assertEqual(w.processed_sequence,n)
                self.assertEqual(w.committed_sequence,n);self.assertEqual(w.outstanding_bytes,0);self.assertEqual(w.stats()['outstanding_items'],0)
                self.assertEqual(self.rows("SELECT count(*) FROM events WHERE kind='BTC'"),[(n,)])
                self.assertEqual(self.rows('PRAGMA integrity_check'),[('ok',)])
                self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])
    async def test_quiet_tail_flush_and_payload_frozen(self):
        w=await self.start();command=self.tick();seq=w.submit(command);command['tick']['price']=1.
        ack=await asyncio.wait_for(w.wait_processed(seq),timeout=5)
        # The process writer now commits each transport batch, so a quiet-tail
        # acknowledgement is also durable.
        self.assertEqual(ack['committed_sequence'],seq)
        await w.stop()
        self.assertEqual(decode(self.rows("SELECT payload_json FROM events WHERE kind='BTC'")[0][0])['price'],50000.)
    async def test_item_limit_explicit_and_stop_reserve(self):
        w=await self.start(max_items=1)
        w.submit(self.tick())
        with self.assertRaises(BufferError):w.submit(self.tick())
        self.assertEqual(w.next_sequence,1)
        await w.stop();self.assertEqual(w.processed_sequence,1)
        self.assertLessEqual(w.high_water_items,2)
    async def test_pending_transport_keeps_sequence_metadata_without_unpickle(self):
        w=await self.start(batch_size=32,flush_seconds=.05)
        seq=w.submit(self.tick())
        self.assertEqual(w.pending[0][0],seq)
        self.assertIsInstance(w.pending[0][1],bytes)
        await w.stop()
    async def test_capacity_rejection_exposes_diagnostics(self):
        w=await self.start(max_items=1)
        w.submit(self.tick())
        with self.assertRaises(BufferError) as caught:w.submit(self.tick())
        self.assertIn('items',str(caught.exception));self.assertEqual(w.stats()['capacity_rejections'],1)
        self.assertEqual(w.stats()['last_capacity_rejection']['kind'],'BTC')
        await w.stop()
    async def test_byte_limit_rejects_without_advancing_sequence(self):
        w=await self.start(max_bytes=32)
        with self.assertRaises(BufferError):w.submit(self.tick())
        self.assertEqual(w.next_sequence,0);await w.stop()
    async def test_worker_exception_terminal_not_clean(self):
        w=await self.start();seq=w.submit({'kind':'INVALID_COMMAND','received_ts_ms':1000})
        with self.assertRaises(RuntimeError):await asyncio.wait_for(w.wait_processed(seq),timeout=5)
        await w.release_failed();self.assertIsNotNone(w.error)
        self.assertEqual(self.rows('SELECT status FROM sessions'),[('FAILED',)])
        self.assertEqual(self.rows("SELECT count(*) FROM events WHERE kind='WRITER_FAILURE'"),[(1,)])
        self.writer=None
    async def test_commit_ack_barrier(self):
        w=await self.start();w.submit(self.tick())
        seq=w.submit({'kind':'FLUSH','received_ts_ms':1001})
        ack=await asyncio.wait_for(w.wait_processed(seq),timeout=5)
        self.assertEqual(ack['committed_sequence'],seq)
        self.assertEqual(self.rows("SELECT count(*) FROM events WHERE kind='BTC'"),[(1,)])
        await w.stop()
    async def test_submit_after_stop_fence_refused(self):
        w=await self.start();w.submit({'kind':'STOP','received_ts_ms':1000})
        with self.assertRaises(RuntimeError):w.submit(self.tick())
        await w.stop()
    async def test_config_and_stop_evidence_survive_process_boundary(self):
        self.writer=ProcessWriter(self.path,config={'depth_levels':20,'timestamp_contract':'D5.1','probe':'yes'})
        await self.writer.start()
        await self.writer.stop(received_ts_ms=2000,status='FAILED',
            payload={'elapsed_seconds':12.5,'collection_seconds':12.0,'collection_stop_ts_ms':1999},
            cleanup_errors=['synthetic cleanup'])
        self.assertEqual(self.rows('SELECT status FROM sessions'),[('FAILED',)])
        stop=decode(self.rows("SELECT payload_json FROM events WHERE kind='COLLECTION_STOP'")[0][0])
        end=decode(self.rows("SELECT payload_json FROM events WHERE kind='SESSION_END'")[0][0])
        self.assertEqual(stop['collection_stop_ts_ms'],1999)
        self.assertEqual(end['collection_seconds'],12.0)
        self.assertEqual(end['cleanup_errors'],['synthetic cleanup'])

if __name__=='__main__':unittest.main()
