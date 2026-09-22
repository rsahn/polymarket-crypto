import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))

from d6.lead_lag import Tick, event_study, pct_move, value_at_or_after


class D6LeadLagTests(unittest.TestCase):
    def test_pct_move(self):
        self.assertAlmostEqual(pct_move(100, 101), .01)

    def test_value_at_or_after(self):
        s = [Tick(100, 1), Tick(200, 2), Tick(300, 3)]
        self.assertEqual(value_at_or_after(s, 201), Tick(300, 3))
        self.assertIsNone(value_at_or_after(s, 301))

    def test_event_study_fixed_horizon(self):
        btc = [Tick(0, 100), Tick(100, 100), Tick(200, 101)]
        poly = [Tick(200, .50), Tick(250, .51), Tick(300, .53)]
        rows = event_study(
            btc, poly, lookback_ms=100, threshold=.005,
            horizons_ms=(50, 100),
        )
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0].btc_return, .01)
        self.assertAlmostEqual(rows[0].poly_change, .01)
        self.assertAlmostEqual(rows[1].poly_change, .03)

    def test_cooldown_declusters_one_btc_impulse(self):
        btc = [Tick(0,100), Tick(100,101), Tick(200,102), Tick(1200,102), Tick(1300,103)]
        poly = [Tick(100,.5,"m",5000), Tick(200,.51,"m",5000), Tick(1300,.52,"m",5000), Tick(1400,.53,"m",5000)]
        rows = event_study(btc, poly, lookback_ms=100, threshold=.005,
                           horizons_ms=(100,), cooldown_ms=1000)
        self.assertEqual([r.anchor_ts_ms for r in rows], [100,1300])

    def test_never_compares_across_market_rotation(self):
        btc = [Tick(0, 100), Tick(100, 100), Tick(200, 101)]
        poly = [
            Tick(200, .90, "old", 250),
            Tick(300, .40, "new", 600),
        ]
        rows = event_study(
            btc, poly, lookback_ms=100, threshold=.005,
            horizons_ms=(100,),
        )
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].poly_change)

    def test_rejects_unsorted_series(self):
        with self.assertRaises(ValueError):
            event_study(
                [Tick(2, 1), Tick(1, 1)],
                [Tick(1, .5)],
                lookback_ms=1,
                threshold=.01,
            )


if __name__ == "__main__":
    unittest.main()
