"""Accounting and leakage invariants, using synthetic data only."""
import unittest

import pandas as pd

from c3_d4_analysis import (FEATURES, META, add_features, entry_signals,
                            load_partition, market_manifest, simulate)


def row(i=1, ts=0, **overrides):
    r = dict.fromkeys(FEATURES, 0.)
    r.update(id=i, anchor_ts_ms=ts, hedge_ts_ms=ts+15000, delay_ms=15000,
             market_slug='btc-updown-5m-1789764300', condition_id='condition',
             market_duration='5m', direction='DOWN->UP', market_start_ms=0,
             market_end_ms=300000, first_ask=.1, first_bid=.08,
             first_ask_qty=100., first_bid_qty=100., opposite_ask=.85,
             opposite_ask_qty=200., opposite_bid=.84, second_ask=.85,
             second_ask_qty=100., time_remaining_ms=300000-ts)
    r.update(overrides)
    return r


def frame(*rows):
    return add_features(pd.DataFrame(rows))


class D4Invariants(unittest.TestCase):
    def test_future_cannot_change_entries(self):
        a = frame(row(), row(2, 1000), row(3, 15000))
        b = a.copy()
        b['second_ask'] = -999
        b['second_ask_qty'] = 0
        b['hedge_ts_ms'] = 999999999
        rule = {'feature': 'opposite_depth_coverage_t0', 'operator': '>=', 'threshold': 1.}
        self.assertEqual(entry_signals(a, rule).id.tolist(), entry_signals(b, rule).id.tolist())
        self.assertEqual(entry_signals(a, rule).id.tolist(), [1, 3])

    def test_label_filter_rejected(self):
        with self.assertRaises(ValueError):
            entry_signals(frame(row()), {'feature':'second_ask','operator':'<=','threshold':1.})

    def test_no_hedge_refund(self):
        for mode, expected in [('v4_proxy', -2.), ('zero_recovery', -10.)]:
            m, ld, mk, _ = simulate(frame(row(second_ask_qty=0.)), mode)
            self.assertAlmostEqual(m['pnl'], expected)
            self.assertAlmostEqual(ld.pnl.sum(), mk.pnl.sum())
            self.assertEqual(m['hedge_impossible'], 1)

    def test_partial_hedge_includes_residual_loss(self):
        m, ld, _, _ = simulate(frame(row(second_ask_qty=50., first_bid_qty=20.)))
        # 50 payout + 20*.08 exit - 10 first leg - 50*.855 second leg = -1.15
        self.assertAlmostEqual(m['pnl'], -1.15)
        self.assertEqual(m['hedge_reduced'], 1)
        self.assertAlmostEqual(ld.iloc[0].zero_value_qty, 30.)

    def test_pair_cash_locked_until_expiry(self):
        m, ld, _, curve = simulate(frame(row()))
        hedge = curve[(curve.ts_ms == 15000) & (curve.event == 1)].iloc[0]
        self.assertAlmostEqual(hedge.cash, 404.5)
        self.assertAlmostEqual(m['final_capital'], 504.5)
        self.assertEqual(curve.iloc[-1].ts_ms, 300000)

    def test_expired_quote_never_pairs(self):
        m, _, _, _ = simulate(frame(row(market_end_ms=10000)))
        self.assertEqual(m['hedge_impossible'], 1)
        self.assertEqual(m['invalid_future_quotes'], 1)

    def test_overlapping_legs_are_financed_at_their_timestamps(self):
        # Second entry happens before first hedge. Both LEG1 costs must be paid first.
        m, ld, _, _ = simulate(frame(row(), row(2, 10000)), initial=25.)
        first = ld[ld.id == 1].iloc[0]
        self.assertAlmostEqual(first.cash_at_hedge_before_exit, 5.)
        self.assertEqual(m['trades'], 2)
        self.assertAlmostEqual(m['pnl'], ld.pnl.sum())

    def test_shared_hedge_snapshot_cannot_be_consumed_twice(self):
        a = row(second_ask_qty=100., hedge_ts_ms=30000, delay_ms=30000)
        b = row(2, 15000, second_ask_qty=100.)
        _, ld, _, _ = simulate(frame(a, b))
        self.assertAlmostEqual(ld.paired_qty.sum(), 100.)

    def test_empty_and_zero_cash(self):
        x = frame(row())
        m, _, _, _ = simulate(x.iloc[:0])
        self.assertEqual(m['final_capital'], 500)
        # Depletion within normal positive initial capital is supported.
        m, ld, _, _ = simulate(frame(row(), row(2, 1000)), initial=10., exit_mode='zero_recovery')
        self.assertEqual(m['skipped_no_cash'], 1)
        self.assertEqual(m['final_capital'], 0)

    def test_drawdown_uses_preceding_peak(self):
        m, _, _, curve = simulate(frame(row(), row(2, 310000, market_end_ms=600000)))
        equity = curve.equity_lower_bound
        peaks = equity.cummax().clip(lower=500.)
        self.assertAlmostEqual(m['max_drawdown_pct'], float(((peaks-equity)/peaks*100).max()))

    def test_split_is_disjoint_and_chronological(self):
        m = pd.DataFrame([dict(market_slug=f'btc-updown-5m-{1789764300+i*300}',
                              market_duration='5m', first_ts=(1789764300+i*300)*1000,
                              last_ts=(1789764300+i*300)*1000+1000, rows=2, conditions=1)
                          for i in range(10)])
        result = market_manifest(m)
        self.assertEqual(result.split.value_counts().to_dict(), {'train':6, 'validation':2, 'oos':2})
        self.assertFalse(result.market_slug.duplicated().any())

    def test_oos_gate_precedes_any_io(self):
        with self.assertRaises(RuntimeError):
            load_partition(None, 'oos')


if __name__ == '__main__':
    unittest.main()
