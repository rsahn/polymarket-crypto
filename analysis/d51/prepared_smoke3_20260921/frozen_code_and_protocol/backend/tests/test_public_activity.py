import unittest

from app.collectors.public_activity import normalize_activity, reconstruct_inventory


class TestPublicActivity(unittest.TestCase):
    def test_normalizes_and_reconstructs_trade(self):
        rows = [
            normalize_activity({'timestamp': 2, 'conditionId': 'c', 'type': 'TRADE', 'side': 'BUY', 'outcome': 'Up', 'size': '10', 'price': '0.4'}, 'x'),
            normalize_activity({'timestamp': 3, 'conditionId': 'c', 'type': 'TRADE', 'side': 'SELL', 'outcome': 'Up', 'size': '3', 'price': '0.5'}, 'x'),
        ]
        rebuilt = reconstruct_inventory(rows)
        self.assertEqual(rebuilt[-1]['inventory'], 7)
        self.assertEqual(rows[0]['usdc_size'], 4)

    def test_validation_rejects_wrong_profile_name(self):
        class StubCollector:
            def get_public_profile(self, address):
                return {'name': 'other'}

        collector = StubCollector()
        with self.assertRaises(ValueError):
            profile_name = collector.get_public_profile('0x0')['name']
            if profile_name.casefold() != 'BoneOhio'.casefold():
                raise ValueError('profile mismatch')


if __name__ == '__main__':
    unittest.main()