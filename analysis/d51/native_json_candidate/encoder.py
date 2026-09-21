"""Experimental only. Semantic JSON equivalence, not byte identity."""
import json, math, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).parent/'vendor'))
import orjson

class Fallback(Exception):
    pass

def validate(value, active):
    t = type(value)
    if t in (str, bool, type(None)):
        return
    if t is int:
        if not -(1 << 63) <= value < (1 << 64):
            raise Fallback()
        return
    if t is float:
        if not math.isfinite(value):
            raise ValueError('Out of range float values are not JSON compliant')
        return
    if t not in (dict, list, tuple):
        raise Fallback()
    ident = id(value)
    if ident in active:
        raise ValueError('Circular reference detected')
    active.add(ident)
    try:
        if t is dict:
            if any(type(k) is not str for k in value):
                raise Fallback()
            children = value.values()
        else:
            children = value
        for item in children:
            validate(item, active)
    finally:
        active.remove(ident)

def encode(value):
    try:
        validate(value, set())
        return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode('utf-8')
    except (Fallback, orjson.JSONEncodeError):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
