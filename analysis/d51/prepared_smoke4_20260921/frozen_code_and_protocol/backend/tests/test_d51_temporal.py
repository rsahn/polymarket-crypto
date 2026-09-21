import unittest
from app.collectors.polymarket_ws import PolymarketOrderbookCollector


def full(token, ts):
    return dict(event_type='book',asset_id=token,timestamp=ts,
                bids=[dict(price='0.40',size='5')],asks=[dict(price='0.60',size='5')])

class D51TemporalTests(unittest.TestCase):
    def collector(self):
        c=PolymarketOrderbookCollector('5m',{'UP':'u','DOWN':'d'},lambda _:None,timestamp_contract='D5.1')
        c.normalize_snapshot([full('u',1000),full('d',1000)],1100)
        return c

    def test_last_trade_does_not_advance_book_clock(self):
        c=self.collector()
        trade=c.normalize_snapshot(dict(event_type='last_trade_price',asset_id='u',timestamp=1507),1600)
        change=c.normalize_snapshot(dict(event_type='price_change',timestamp=1001,
            price_changes=[dict(asset_id='u',price='0.40',size='6',side='BUY')]),1601)
        self.assertEqual(trade['wire_event_ts_ms'],1507)
        self.assertEqual(trade['event_ts_ms'],1000)
        self.assertEqual(change['event_ts_ms'],1001)
        self.assertEqual(change['up']['event_ts_ms'],1001)
        self.assertEqual(change['down']['event_ts_ms'],1000)
        self.assertEqual(change['received_ts_ms'],1601)
        self.assertEqual(change['down']['received_ts_ms'],1100)
        self.assertEqual(trade['source_metadata'][0]['timestamp'],1507)

    def test_max_is_current_sides_not_wire_order(self):
        c=self.collector()
        s=c.normalize_snapshot([full('u',1200),full('d',1100)],1300)
        self.assertEqual(s['event_ts_ms'],1200)
        self.assertEqual(s['wire_event_ts_ms'],1100)

    def test_rejects_within_message_regression_atomically(self):
        c=self.collector(); before=dict(c._last_source_ts)
        s=c.normalize_snapshot([full('u',1200),full('u',1100)],1300)
        self.assertEqual(s['reject_reason'],'OUT_OF_ORDER')
        self.assertEqual(c._last_source_ts,before)

    def test_missing_source_rejected(self):
        c=self.collector(); s=c.normalize_snapshot(full('u',None),1300)
        self.assertEqual(s['reject_reason'],'MISSING_EVENT_TIMESTAMP')

    def test_generation_reset_requires_both_fresh_sides(self):
        c=self.collector(); c._reset_connection_state()
        s=c.normalize_snapshot(full('u',900),1400)
        self.assertIsNone(s['event_ts_ms'])
        self.assertFalse(s['book_generation_ready'])
        s=c.normalize_snapshot(full('d',950),1401)
        self.assertEqual(s['event_ts_ms'],950)
        self.assertTrue(s['book_generation_ready'])

    def test_legacy_envelope_unchanged(self):
        c=PolymarketOrderbookCollector('5m',{'UP':'u','DOWN':'d'},lambda _:None)
        s=c.normalize_snapshot([full('u',1200),full('d',1100)],1300)
        self.assertEqual(s['event_ts_ms'],1100)
        self.assertNotIn('timestamp_contract',s)
