import math,pathlib,tempfile,unittest
from app.d5.store import Store
class DepthCacheTests(unittest.TestCase):
    def test_bytes_exact_for_both_schemas_mutation_and_signed_zero(self):
        for compressed in (False,True):
            with tempfile.TemporaryDirectory() as d:
                s=Store(pathlib.Path(d)/'new.db',compress_payloads=compressed)
                values=[[],[[0,1]],[[0.,1.]], [[-0.,1.]], [[i/100,1000.123456789+i] for i in range(20)]]
                for v in values:
                    expected=s.pack(v)
                    self.assertEqual(s.pack_depth(v),expected);self.assertEqual(s.pack_depth(v),expected)
                v=[[.2,3.]];s.pack_depth(v);v[0][1]=4.;self.assertEqual(s.pack_depth(v),s.pack(v))
                self.assertNotEqual(s.pack_depth([[0.,1.]]),s.pack_depth([[-0.,1.]]))
                self.assertGreater(s.depth_cache_hits,0);s.close()
    def test_capacity_eviction_and_clear(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(pathlib.Path(d)/'new.db',compress_payloads=True)
            for i in range(300):self.assertEqual(s.pack_depth([[.5,i]]),s.pack([[.5,i]]))
            self.assertEqual(len(s._depth_cache),256)
            self.assertEqual(s.pack_depth([[.5,0]]),s.pack([[.5,0]]));s.close();self.assertFalse(s._depth_cache)
    def test_nonfinite_still_rejected_and_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(pathlib.Path(d)/'new.db',compress_payloads=True)
            for value in (math.nan,math.inf,-math.inf):
                with self.assertRaises(ValueError):s.pack_depth([[.5,value]])
            self.assertFalse(s._depth_cache);s.close()
