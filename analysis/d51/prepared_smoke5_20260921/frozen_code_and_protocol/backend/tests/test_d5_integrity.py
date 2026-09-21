import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.d5.audit import audit, cli
from app.d5.features import BTCFeatures
from app.d5.identity import MarketIdentity
from app.d5.store import Store
from test_d5 import identity, snapshot
from app.d5.observer import Observer


class D5IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'instrumentation.db'
        self.store = Store(self.path)
        self.observer = Observer(self.store)
        self.market = identity()
        self.observer.activate(self.market, 1, 0)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_source_at_expiry_is_rejected(self):
        for field in ('envelope', 'up', 'down'):
            book = snapshot(self.market, wire_hash=field)
            target = book if field == 'envelope' else book[field]
            target['event_ts_ms'] = self.market.expiry_ts_ms
            with self.subTest(field=field):
                self.assertIsNone(self.observer.observe(self.market, 1, book, {}, 1000))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE kind='BOOK'").fetchone()[0], 0)

    def test_availability_past_expiry_rejects_book_without_partial_write(self):
        self.store.event('CLOCK', {}, received_ts_ms=100001, available_ts_ms=100001)
        self.assertIsNone(self.observer.observe(self.market, 1, snapshot(self.market), {}, 1000))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE kind='BOOK'").fetchone()[0], 0)

    def test_store_rejects_wrong_identity_without_assert_dependency(self):
        book = snapshot(self.market)
        book['token_up'] = 'FOREIGN'
        with self.assertRaises(ValueError):
            self.store.book(book, self.market, 1, 1000)

    def test_audit_reports_missing_book_side(self):
        eid = self.observer.observe(self.market, 1, snapshot(self.market), {}, 1000)
        self.store.db.execute("DELETE FROM book_sides WHERE event_id=? AND side='UP'", (eid,))
        self.store.flush()
        report = audit(self.path)
        self.assertEqual(report['INCOMPLETE_BOOK_EVENTS'], 1)
        self.assertIn('INTEGRITY_VIOLATION', report['SMOKE_FAILURES'])

    def test_store_rejects_source_expiry_directly(self):
        book = snapshot(self.market)
        book['down']['event_ts_ms'] = self.market.expiry_ts_ms
        with self.assertRaisesRegex(ValueError, 'POST_EXPIRY_REJECT'):
            self.store.book(book, self.market, 1, 1000)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE kind='BOOK'").fetchone()[0], 0)

    def test_full_synthetic_coverage_passes_then_corrupt_side_fails(self):
        self.observer.observe(self.market, 1, snapshot(self.market), {}, 1000)
        self.observer.activate(self.market, 2, 2000)
        self.observer.observe(self.market, 2, snapshot(self.market, 2000), {}, 2000)
        second = identity('B')
        self.observer.activate(second, 3, 3000)
        self.observer.observe(second, 3, snapshot(second, 3000), {}, 3000)
        longer = MarketIdentity('15m', 'C', 'condition_C', 'C_UP', 'C_DOWN', 200000)
        self.observer.activate(longer, 1, 4000)
        eid = self.observer.observe(longer, 1, snapshot(longer, 4000), {}, 4000)
        self.store.event('BTC', {'price': 100.}, received_ts_ms=4000,
                         event_ts_ms=4000, available_ts_ms=4000)
        self.store.flush()
        self.assertTrue(audit(self.path)['SMOKE_VALIDATED'])
        self.store.db.execute("UPDATE book_sides SET event_ts_ms=? WHERE event_id=? AND side='UP'",
                              (longer.expiry_ts_ms, eid))
        self.store.flush()
        report = audit(self.path)
        self.assertEqual(report['POST_EXPIRY_BOOK_SIDES'], 1)
        self.assertFalse(report['SMOKE_VALIDATED'])
        self.assertEqual(report['SMOKE_FAILURES'], ['INTEGRITY_VIOLATION'])

    def test_audit_export_cannot_overwrite_database(self):
        self.store.flush()
        before = self.path.read_bytes()
        with patch('sys.argv', ['audit_d5', '--db', str(self.path), '--out', str(self.path)]):
            with self.assertRaises(SystemExit) as exc:
                cli()
        self.assertEqual(exc.exception.code, 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_audit_export_cannot_overwrite_existing_report(self):
        report = Path(self.tmp.name) / 'report.json'
        report.write_text('existing evidence', encoding='utf-8')
        with patch('sys.argv', ['audit_d5', '--db', str(self.path), '--out', str(report)]):
            with self.assertRaises(SystemExit) as exc:
                cli()
        self.assertEqual(exc.exception.code, 2)
        self.assertEqual(report.read_text(encoding='utf-8'), 'existing evidence')


class D5FeatureIntegrityTests(unittest.TestCase):
    def test_lagged_price_requires_source_available_at_lag_boundary(self):
        features = BTCFeatures()
        features.update(1000, {'recv_ts_ms': 1000, 'event_ts_ms': 1800, 'price': 100.})
        features.update(2000, {'recv_ts_ms': 2000, 'event_ts_ms': 2000, 'price': 101.})
        self.assertIsNone(features.at(2000)['btc_return_1000ms'])


if __name__ == '__main__':
    unittest.main()
