import unittest

from app.collectors.polymarket import PolymarketMarketDiscovery


class TestPolymarketDiscovery(unittest.TestCase):
    def test_finds_active_5m_and_15m_btc_markets(self):
        payload = [
            {
                "slug": "will-bitcoin-go-up-in-5-minutes",
                "question": "Will BTC be above 5m future price in 5 minutes?",
                "outcomes": [
                    {"id": "yes-5m", "label": "Yes", "price": 0.54},
                    {"id": "no-5m", "label": "No", "price": 0.46},
                ],
                "active": True,
            },
            {
                "slug": "will-bitcoin-go-up-in-15-minutes",
                "question": "Will BTC be above 15m future price in 15 minutes?",
                "outcomes": [
                    {"id": "yes-15m", "label": "Yes", "price": 0.57},
                    {"id": "no-15m", "label": "No", "price": 0.43},
                ],
                "active": True,
            },
            {
                "slug": "will-eth-go-up-in-5-minutes",
                "question": "Will ETH be above 5m future price in 5 minutes?",
                "outcomes": [
                    {"id": "eth-yes", "label": "Yes", "price": 0.49},
                    {"id": "eth-no", "label": "No", "price": 0.51},
                ],
                "active": True,
            },
        ]

        result = PolymarketMarketDiscovery.parse_market_list(payload)

        self.assertEqual(len(result), 2)
        self.assertIn('5m', result[0]['market_key'])
        self.assertIn('15m', result[1]['market_key'])
        self.assertEqual(result[0]['token_ids']['UP'], 'yes-5m')
        self.assertEqual(result[0]['token_ids']['DOWN'], 'no-5m')


if __name__ == '__main__':
    unittest.main()
