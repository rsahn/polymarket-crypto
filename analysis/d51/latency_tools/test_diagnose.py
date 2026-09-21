import unittest
from diagnose import Histogram
class HistogramTests(unittest.TestCase):
    def test_exact_bins_missing_negative_and_strict_thresholds(self):
        h=Histogram()
        for x in [-2,0,1000,1001,5000,5001,None,True,1.25]:h.add(x)
        r=h.report();self.assertEqual(r['n'],6);self.assertEqual(r['missing'],1);self.assertEqual(r['invalid'],2)
        self.assertEqual(r['negative_count'],1);self.assertEqual(r['quantiles_ms'],{'p50':1000,'p95':5001,'p99':5001})
        self.assertEqual(r['over_ms']['5000']['count'],1);self.assertEqual(r['over_ms']['1000']['count'],3)
        self.assertEqual(r['histogram_ms'],[(-2,1),(0,1),(1000,1),(1001,1),(5000,1),(5001,1)])
    def test_empty_has_no_fabricated_percentile(self):
        r=Histogram().report();self.assertEqual(r['quantiles_ms'],{});self.assertIsNone(r['mean_ms']);self.assertIsNone(r['over_ms']['1000']['fraction'])
