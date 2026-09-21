import pathlib,tempfile,sqlite3,unittest
from contextlib import closing
from app.d5.store import Store
from app.d5.quality51 import supplement
from test_d5 import identity,snapshot

class WireAuditTests(unittest.TestCase):
    def test_wire_timestamp_must_match_preserved_message(self):
        with tempfile.TemporaryDirectory() as t:
            path=pathlib.Path(t)/'synthetic.db';s=Store(path,compress_payloads=True);m=identity();s.market(m,{})
            book=snapshot(m,1000,timestamp_contract='D5.1',wire_event_ts_ms=1500,book_state_source_ts_ms=1000,source_metadata=[{'timestamp':1200}])
            for side in ('up','down'):book[side]['received_ts_ms']=1000
            s.book(book,m,1,1000);sid=s.session_id;s.close()
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:r=supplement(db,sid,1000,1100)
            self.assertIn('WIRE_RAW_TIMESTAMP_MISMATCH',r['failures'])

    def test_real_mixed_messages_preserve_raw_regression_as_diagnostic(self):
        from app.collectors.polymarket_ws import PolymarketOrderbookCollector
        from test_d51_temporal import full
        with tempfile.TemporaryDirectory() as t:
            path=pathlib.Path(t)/'synthetic.db';store=Store(path,compress_payloads=True);m=identity();store.market(m,{})
            c=PolymarketOrderbookCollector('5m',{'UP':m.token_up,'DOWN':m.token_down},lambda _:None,expiry_ts_ms=m.expiry_ts_ms,identity=m,timestamp_contract='D5.1')
            c.normalize_snapshot([full(m.token_up,1000),full(m.token_down,1000)],1100)
            trade=c.normalize_snapshot(dict(event_type='last_trade_price',asset_id=m.token_up,timestamp=1507),1600)
            change=c.normalize_snapshot(dict(event_type='price_change',timestamp=1001,price_changes=[dict(asset_id=m.token_up,price='0.40',size='6',side='BUY')]),1601)
            store.book(trade,m,1,1600);store.book(change,m,1,1601)
            store.event('COLLECTION_STOP',{},received_ts_ms=1700,available_ts_ms=1700)
            store.event('SESSION_END',{},received_ts_ms=1701,available_ts_ms=1701)
            sid=store.session_id;store.close()
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:r=supplement(db,sid,1600,1700)
            self.assertEqual(r['wire_regressions_diagnostic_only'],1)
            self.assertEqual(r['wire_worst_regression_ms'],506)
            self.assertNotIn('WIRE_RAW_TIMESTAMP_MISMATCH',r['failures'])
            self.assertNotIn('BOOK_SOURCE_REGRESSION',r['failures'])
            self.assertNotIn('SQL_SIDE_METADATA_MISMATCH',r['failures'])
            self.assertNotIn('STOP_MARKERS_MISSING_OR_DUPLICATE',r['failures'])
