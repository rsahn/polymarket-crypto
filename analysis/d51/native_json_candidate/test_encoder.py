import json, math, unittest
from encoder import encode

def typed(value):
    if isinstance(value, float):return ('float',value.hex())
    if isinstance(value, list):return ('list',[typed(v) for v in value])
    if isinstance(value, dict):return ('dict',{k:typed(v) for k,v in value.items()})
    return (type(value).__name__,value)

class EncoderTests(unittest.TestCase):
    def test_values_types_unicode_and_float_bits(self):
        cases = [None,True,False,{},[],[1,1.0,-0.0,0.0,5e-324,1e308,1e-20],{'é':'😀','x':'\ud800'},[2**100,-2**100],{'a':(1,2.0)}, {1:'x'}, {'x':[float.fromhex('0x1.fffffffffffffp+1023')]}]
        for value in cases:
            with self.subTest(value=repr(value)):
                expected=json.loads(json.dumps(value,allow_nan=False))
                self.assertEqual(typed(expected),typed(json.loads(encode(value))))
    def test_nonfinite_rejected_even_nested(self):
        for v in (float('nan'),float('inf'),float('-inf')):
            with self.assertRaises(ValueError):encode({'x':[v]})
    def test_cycle_and_unsupported_rejected(self):
        v=[];v.append(v)
        with self.assertRaises(ValueError):encode(v)
        with self.assertRaises(TypeError):encode({'x':object()})
