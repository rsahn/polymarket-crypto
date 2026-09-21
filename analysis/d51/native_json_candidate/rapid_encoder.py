import json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).parent/'rapid_vendor'))
import rapidjson

def encode(value):
    try:
        return rapidjson.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                               number_mode=rapidjson.NM_NATIVE, bytes_mode=rapidjson.BM_NONE,
                               iterable_mode=rapidjson.IM_ONLY_LISTS)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
