import unittest
from app.collectors.polymarket_ws import PolymarketOrderbookCollector

class DuplicateIndexTests(unittest.TestCase):
    def test_window_eviction_rejection_and_reconnection(self):
        c = PolymarketOrderbookCollector('5m', {'UP':'u','DOWN':'d'}, None, timestamp_contract='D5.1')
        def event(n):
            return {'event_type':'last_trade_price','asset_id':'u','timestamp':1000,'sequence':n}
        for n in range(2048):
            self.assertNotIn('reject_reason', c.normalize_snapshot(event(n), 2000+n))
        self.assertEqual(c.normalize_snapshot(event(0), 5000)['reject_reason'], 'DUPLICATE_EVENT')
        self.assertEqual(len(c._wire_seen), 2048)
        c.normalize_snapshot(event(2048), 5001)
        self.assertNotIn('reject_reason', c.normalize_snapshot(event(0), 5002))
        self.assertEqual(set(c._wire_seen), c._wire_seen_index)
        self.assertEqual(len(c._wire_seen_index), 2048)
        c._reset_connection_state()
        self.assertEqual(len(c._wire_seen_index), 0)
        self.assertNotIn('reject_reason', c.normalize_snapshot(event(0), 5003))
