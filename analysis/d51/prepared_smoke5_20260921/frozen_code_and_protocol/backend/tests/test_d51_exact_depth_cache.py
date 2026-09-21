import unittest
from collections import OrderedDict
from app.d5.store import Store
CachedStore = Store

class ExactCacheTests(unittest.TestCase):
    def store(self):
        s=object.__new__(CachedStore);s.schema_version=2;s.depth_cache=OrderedDict();s.cache_hits=0;s.cache_misses=0
        return s
    def test_bits_types_mutation_and_bound(self):
        s=self.store()
        cases=[[[0.0,1.0]],[[-0.0,1.0]],[[0,1]],[(0.0,1.0)],[],[[0.5,2.0]]*20]
        for v in cases*2:self.assertEqual(s.pack(v),s._pack_uncached(v))
        v=[[0.2,1.0]];s.pack(v);v[0][1]=2.0
        self.assertEqual(s.pack(v),s._pack_uncached(v))
        for n in range(1100):s.pack([[float(n),1.0]])
        self.assertEqual(len(s.depth_cache),1024)
        self.assertGreater(s.cache_hits,0)
    def test_nonfinite_not_hidden_by_cache(self):
        s=self.store()
        for v in (float('nan'),float('inf'),float('-inf')):
            for _ in range(2):
                with self.assertRaises(ValueError):s.pack([[0.1,v]])
        self.assertEqual(len(s.depth_cache),0)
