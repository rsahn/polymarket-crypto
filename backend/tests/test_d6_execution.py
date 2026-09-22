import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"analysis"))
from d6.execution_sim import _fill
class D6ExecutionTests(unittest.TestCase):
 def test_walks_depth_and_vwap(self):
  cost,shares,vwap=_fill([[.5,100],[.6,100]],80)
  self.assertAlmostEqual(cost,80);self.assertAlmostEqual(shares,150);self.assertAlmostEqual(vwap,80/150)
 def test_depth_caps_budget(self):
  cost,shares,vwap=_fill([[.5,10]],500)
  self.assertEqual(cost,5);self.assertEqual(shares,10);self.assertEqual(vwap,.5)
if __name__=="__main__":unittest.main()
