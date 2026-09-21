import unittest
from unittest.mock import patch
from app.collectors.stage_timing import StageTiming

class StageTimingTests(unittest.TestCase):
    def test_accumulation_and_independent_snapshot(self):
        t = StageTiming()
        with patch('app.collectors.stage_timing.time.perf_counter_ns', side_effect=[10, 60_000_010, 100, 1_000_100]), patch('app.collectors.stage_timing.time.thread_time_ns', side_effect=[0, 1_000_000, 2_000_000, 2_500_000]):
            t.finish('write', t.start())
            before = t.snapshot()
            t.finish('write', t.start())
        self.assertEqual(before['write']['calls'], 1)
        self.assertEqual(t.snapshot()['write'], dict(calls=2, wall_ns=61_000_000, cpu_ns=1_500_000, max_wall_ns=60_000_000, over_5ms=1, over_50ms=1))
