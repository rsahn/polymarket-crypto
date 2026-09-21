import asyncio
from contextlib import closing
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.d5.audit import audit
from app.d5.live import run
from app.d5.observer import Observer
from app.d5.prospective import validate_paths
from app.d5.quality import quality_gate, review
from app.d5.store import Store, decode
from test_d5 import identity, snapshot


class ProspectiveTests(unittest.TestCase):
    def test_compression_preserves_all_values_and_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'new.db'
            s=Store(p,compress_payloads=True)
            m=identity()
            book=snapshot(m)
            book['padding']='raw observation '*1000
            o=Observer(s); o.activate(m,1,0)
            eid=o.observe(m,1,book,{},1000)
            raw,source,received,available=s.db.execute('SELECT payload_json,event_ts_ms,received_ts_ms,available_ts_ms FROM events WHERE event_id=?',(eid,)).fetchone()
            self.assertIsInstance(raw,bytes)
            self.assertEqual(decode(raw),book)
            self.assertEqual((source,received,available),(1000,1000,1000))
            self.assertEqual(s.db.execute('SELECT version FROM schema_info').fetchone()[0],2)
            s.event('SESSION_END',{'elapsed_seconds':12,'collection_seconds':2,'collection_stop_ts_ms':2000},received_ts_ms=12000,available_ts_ms=12000)
            sid=s.session_id
            s.close()
            self.assertEqual(audit(p)['ROWS'],1)
            out=Path(tmp)/'review'; out.mkdir()
            result=review(p,out,sid)
            self.assertTrue(result['REPLAY_HASHES_EQUAL'])
            self.assertTrue(result['NO_TRADE_VERIFIED'])
            self.assertFalse(result['RESEARCH_ALLOWED'])
            self.assertIn('DURATION_BELOW_24H',result['QUALITY_FAILURES'])
            self.assertEqual(result['OPEN_ANCHORS'],0)
            self.assertEqual(result['ACTUAL_DURATION_SECONDS'],2)
            self.assertEqual(result['SESSION_ELAPSED_SECONDS'],12)
            self.assertEqual(result['FEED_GAPS']['5m']['trailing_gap_ms'],1000)
            self.assertEqual(result['SQLITE_INTEGRITY_CHECK'],['ok'])
            for key in ('ROTATIONS','RECONNECTIONS','FEED_GAPS','POST_EXPIRY_ACCEPTED','OUT_OF_ORDER_REJECTED'):
                self.assertIn(key,result)

    def test_new_database_required_and_production_duration_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=root/'d5_live_24h_20260920_120000.db'; out=root/'result'
            with self.assertRaises(ValueError): validate_paths(db,out,3600,False)
            validate_paths(db,out,86400,False)
            db.write_bytes(b'historical evidence')
            with self.assertRaises(FileExistsError): validate_paths(db,out,86400,False)
            self.assertEqual(db.read_bytes(),b'historical evidence')

    def test_existing_schema_cannot_be_silently_converted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'existing.db'; s=Store(p); s.close()
            before=p.read_bytes()
            with self.assertRaises(ValueError): Store(p,compress_payloads=True)
            self.assertEqual(p.read_bytes(),before)

    def test_quality_gate_requires_full_duration_clean_data_and_equal_replays(self):
        report={'SMOKE_FAILURES':[],'SESSION':{'status':'STOPPED'},'ACTUAL_DURATION_SECONDS':86401,
                'SQLITE_INTEGRITY_CHECK':['ok'],'FOREIGN_KEY_VIOLATIONS':[],'OPEN_ANCHORS':0,
                'POST_EXPIRY_ACCEPTED':0,'FEED_GAPS':{name:{'coverage_seconds':86400,'gaps_over_5s':0,
                'initial_gap_ms':500,'trailing_gap_ms':500,'receive_regressions':0} for name in ('5m','15m','BTC')}}
        self.assertEqual(quality_gate(report,True),[])
        report['SMOKE_FAILURES']=['RECONNECT_NOT_OBSERVED']
        self.assertEqual(quality_gate(report,True),[])
        self.assertIn('REPLAY_FAILED_OR_DIFFERENT',quality_gate(report,False))
        report['FEED_GAPS']['15m']['gaps_over_5s']=1
        self.assertIn('GAPS_REQUIRE_REVIEW_15m',quality_gate(report,True))


class RunnerFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_collector_is_not_marked_cleanly_stopped(self):
        class Broken:
            async def run(self): raise RuntimeError('synthetic transport failure')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'failure.db'
            args=SimpleNamespace(db=path,seconds=1,reconnect_after=0,compress_payloads=True,min_free_bytes=0)
            with patch('app.d5.live.BinanceCollector',return_value=Broken()), patch('app.d5.live.PolymarketMarketDiscovery.get_active_btc_markets',return_value=[]):
                with self.assertRaisesRegex(RuntimeError,'synthetic transport failure'):
                    await run(args)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT status FROM sessions').fetchone()[0],'FAILED')
                self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='SESSION_END'").fetchone()[0],1)


if __name__=='__main__': unittest.main()
