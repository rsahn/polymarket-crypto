import os
import sqlite3
import uuid
import unittest

from backend.collectors.binance.btc_collector import BinanceBTCCollector
from backend.storage.sqlite_store import SqliteStore


class TestPhaseABTCCollector(unittest.TestCase):
    def _create_db_path(self):
        base_dir = os.path.dirname(__file__)
        return os.path.join(base_dir, f'phase_a_test_{uuid.uuid4().hex}.db')

    def test_db_initializes_required_tables(self):
        db_path = self._create_db_path()
        store = SqliteStore(db_path)

        try:
            with sqlite3.connect(db_path) as conn:
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('btc_ticks','market_ticks','orderbook_snapshots')"
                ).fetchall()
            self.assertEqual({row[0] for row in tables}, {'btc_ticks', 'market_ticks', 'orderbook_snapshots'})
        finally:
            store.close()

    def test_trade_and_booktick_are_normalized(self):
        db_path = self._create_db_path()
        if os.path.exists(db_path):
            os.unlink(db_path)
        store = SqliteStore(db_path)
        collector = BinanceBTCCollector(store)

        trade = {
            'e': 'trade',
            'E': 1700000000000,
            's': 'BTCUSDT',
            'p': '64000.00',
            'q': '0.75',
            'T': 1700000000100,
        }
        book = {
            'u': 123,
            's': 'BTCUSDT',
            'b': '63998.50',
            'B': '1.5',
            'a': '64001.50',
            'A': '2.1',
        }

        collector.process_trade_event(trade)
        collector.process_bookticker_event(book)

        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute('SELECT event_type, symbol, price, quantity, bid, ask FROM btc_ticks ORDER BY id').fetchall()

            self.assertEqual(rows[0][0], 'trade')
            self.assertEqual(rows[0][1], 'BTCUSDT')
            self.assertEqual(float(rows[0][2]), 64000.0)
            self.assertEqual(float(rows[0][3]), 0.75)
            self.assertEqual(rows[1][0], 'bookTicker')
            self.assertEqual(float(rows[1][4]), 63998.5)
            self.assertEqual(float(rows[1][5]), 64001.5)
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
