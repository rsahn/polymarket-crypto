"""Experimental codec only. Not a schema-2 writer or production decoder."""
import math,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
import msgpack
PREFIX=b'D51M1\0'

def valid(value):
    t=type(value)
    if value is None or t in (str,bool):return True
    if t is int:return -(1<<63)<=value<(1<<64)
    if t is float:return math.isfinite(value)
    if t in (list,tuple):return all(valid(x) for x in value)
    if t is dict:return all(type(k) is str and valid(v) for k,v in value.items())
    return False

def pack(value):
    if not valid(value):raise ValueError('Unsupported or nonfinite value')
    raw=msgpack.packb(value,use_bin_type=True,use_single_float=False)
    compressed=zlib.compress(raw,1) if len(raw)>=512 else raw
    return PREFIX+(b'Z'+compressed if len(compressed)<len(raw) else b'R'+raw)

def unpack(value):
    if not value.startswith(PREFIX):raise ValueError('Invalid format')
    tag=value[len(PREFIX):len(PREFIX)+1];body=value[len(PREFIX)+1:]
    if tag==b'Z':body=zlib.decompress(body)
    elif tag!=b'R':raise ValueError('Invalid compression tag')
    return msgpack.unpackb(body,raw=False,strict_map_key=True)
