import time
import unittest

from app.collectors.polymarket_ws import PolymarketOrderbookCollector


class TestPolymarketOrderbookCollector(unittest.TestCase):
    def test_normalizes_market_snapshot(self):
        collector = PolymarketOrderbookCollector('5m', {'UP': 'yes-5m', 'DOWN': 'no-5m'}, lambda *_: None)

        payload = {
            'type': 'book',
            'market': 'btcusdt-up-down-5m',
            'event_ts_ms': 1700000000000,
            'bids': [{'price': '0.54', 'quantity': '1.20'}],
            'asks': [{'price': '0.58', 'quantity': '0.80'}],
            'outcomes': {
                'yes-5m': {'best_bid': 0.54, 'best_ask': 0.58, 'bid_quantity': 1.2, 'ask_quantity': 0.8},
                'no-5m': {'best_bid': 0.47, 'best_ask': 0.49, 'bid_quantity': 1.1, 'ask_quantity': 1.7},
            },
            'end_date_ts': int(time.time() * 1000) + 30000,
        }

        # Test the actual CLOB book-array protocol, not a retired dashboard envelope.
        normalized = collector.normalize_snapshot([
            {'asset_id':token,'event_ts_ms':payload['event_ts_ms'],
             'end_date_ts':payload['end_date_ts'],
             'bids':[{'price':q['best_bid'],'size':q['bid_quantity']}],
             'asks':[{'price':q['best_ask'],'size':q['ask_quantity']}]}
            for token,q in payload['outcomes'].items()
        ])

        self.assertEqual(normalized['market_key'], '5m')
        self.assertEqual(normalized['token_ids']['UP'], 'yes-5m')
        self.assertGreaterEqual(normalized['time_remaining_ms'], 29000)
        self.assertEqual(normalized['up']['bid'], 0.54)
        self.assertEqual(normalized['down']['ask'], 0.49)

    def test_normalizes_clob_book_array_and_price_change(self):
        collector = PolymarketOrderbookCollector('5m', {'UP': 'yes-5m', 'DOWN': 'no-5m'}, lambda *_: None)
        collector.normalize_snapshot([
            {'asset_id': 'yes-5m', 'timestamp': '1700000000000', 'bids': [{'price': '0.54', 'size': '2'}], 'asks': [{'price': '0.58', 'size': '3'}]},
            {'asset_id': 'no-5m', 'timestamp': '1700000000000', 'bids': [{'price': '0.47', 'size': '4'}], 'asks': [{'price': '0.49', 'size': '5'}]},
        ])
        normalized = collector.normalize_snapshot({
            'event_type': 'price_change',
            'timestamp': '1700000000100',
            'price_changes': [{'asset_id': 'yes-5m', 'price': '0.56', 'size': '7', 'side': 'BUY'}],
        })
        self.assertEqual(normalized['up']['bid'], 0.56)
        self.assertEqual(normalized['up']['bid_qty'], 7.0)

    def test_ignores_stale_token_event(self):
        collector = PolymarketOrderbookCollector('5m', {'UP': 'new-up', 'DOWN': 'new-down'}, lambda *_: None)
        normalized = collector.normalize_snapshot({
            'asset_id': 'old-up', 'timestamp': str(int(time.time() * 1000)),
            'bids': [{'price': '0.87', 'size': '10'}], 'asks': [{'price': '0.88', 'size': '10'}],
        })
        self.assertTrue(normalized['stale_token'])
        self.assertIsNone(collector._books.get('new-up'))

    def test_new_book_is_incomplete_until_both_tokens_exist(self):
        collector = PolymarketOrderbookCollector('5m', {'UP': 'new-up', 'DOWN': 'new-down'}, lambda *_: None)
        first = collector.normalize_snapshot({'asset_id': 'new-up', 'bids': [{'price': '0.50', 'size': '2'}], 'asks': [{'price': '0.51', 'size': '2'}]})
        self.assertIsNotNone(first['up']['bid'])
        self.assertIsNone(first['down']['bid'])
        second = collector.normalize_snapshot({'asset_id': 'new-down', 'bids': [{'price': '0.49', 'size': '2'}], 'asks': [{'price': '0.50', 'size': '2'}]})
        self.assertIsNotNone(second['up']['ask'])
        self.assertIsNotNone(second['down']['bid'])


if __name__ == '__main__':
    unittest.main()
