"""Lossless framed SQLite-row archive candidate; no collector or economic access."""
import base64,hashlib,json,os,struct,zlib
from collections import OrderedDict
from pathlib import Path

MAGIC=b"PVA1\n"; HEADER=struct.Struct("<II32s32s")
BLOCK=1024*1024; LIMIT=4*1024*1024

class Codec:
    def __init__(self,limit=16*1024*1024):
        self.cache=OrderedDict();self.cache_bytes=0;self.limit=limit
    def cached(self,key,make):
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key][0]
        value=make();weight=len(key[1])+(len(value) if isinstance(value,bytes) else len(json.dumps(value)))+64
        if weight<=self.limit:
            while self.cache and self.cache_bytes+weight>self.limit:
                _,(_,old)=self.cache.popitem(last=False);self.cache_bytes-=old
            self.cache[key]=(value,weight);self.cache_bytes+=weight
        return value
    def encode(self,value):
        if isinstance(value,bytes):
            def make():
                try:
                    d=zlib.decompressobj();raw=d.decompress(value,LIMIT+1)
                    if len(raw)<=LIMIT and d.eof and not d.unused_data and zlib.compress(raw,1)==value:
                        return ["Z1",raw.decode("utf-8")]
                except (zlib.error,UnicodeError):pass
                return ["B",base64.b64encode(value).decode("ascii")]
            return self.cached(("E",value),make)
        if isinstance(value,float):return ["F",value.hex()]
        return value
    def decode(self,value):
        if isinstance(value,list):
            if value[0]=="Z1":
                raw=value[1].encode("utf-8")
                return self.cached(("D",raw),lambda:zlib.compress(raw,1))
            if value[0]=="B":return base64.b64decode(value[1],validate=True)
            if value[0]=="F":return float.fromhex(value[1])
            raise ValueError("UNKNOWN_TYPE")
        return value

def canonical(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")

class ArchiveWriter:
    def __init__(self,path):
        self.file=Path(path).open("xb");self.file.write(MAGIC)
        self.buffer=bytearray();self.previous=bytes(32);self.frames=0;self.rows=0
        self.raw_bytes=0;self.poisoned=False;self.closed=False
    def append(self,record):
        if self.closed or self.poisoned:raise ValueError("ARCHIVE_CLOSED_OR_POISONED")
        line=canonical(record)+b"\n"
        if len(line)>LIMIT:raise ValueError("RECORD_TOO_LARGE")
        if self.buffer and len(self.buffer)+len(line)>BLOCK:self.flush()
        self.buffer.extend(line);self.rows+=1
    def flush(self):
        if self.poisoned:raise ValueError("ARCHIVE_POISONED")
        if not self.buffer:return
        raw=bytes(self.buffer);packed=zlib.compress(raw,6);h=hashlib.sha256(raw).digest()
        header=HEADER.pack(len(raw),len(packed),h,self.previous)
        try:
            if self.file.write(header+packed)!=len(header)+len(packed):raise OSError("SHORT_WRITE")
            self.file.flush();os.fsync(self.file.fileno())
        except BaseException:self.poisoned=True;raise
        self.raw_bytes+=len(raw);self.frames+=1;self.previous=h;self.buffer.clear()
    def close(self):
        if self.closed:return
        try:
            if not self.poisoned:
                self.flush();footer=HEADER.pack(0,0,bytes(32),self.previous)
                if self.file.write(footer)!=len(footer):raise OSError("SHORT_WRITE")
                self.file.flush();os.fsync(self.file.fileno())
        finally:self.file.close();self.closed=True

def stream_archive(path):
    previous=bytes(32)
    with Path(path).open("rb") as f:
        if f.read(len(MAGIC))!=MAGIC:raise ValueError("FORMAT")
        while True:
            header=f.read(HEADER.size)
            if len(header)!=HEADER.size:raise ValueError("TORN_ARCHIVE")
            rawlen,packedlen,h,prev=HEADER.unpack(header)
            if prev!=previous:raise ValueError("CHAIN_BREAK")
            if rawlen==packedlen==0:
                if h!=bytes(32) or f.read(1):raise ValueError("BAD_FOOTER")
                return
            if not 0<rawlen<=LIMIT or not 0<packedlen<=LIMIT+1024:raise ValueError("FRAME_SIZE")
            packed=f.read(packedlen)
            if len(packed)!=packedlen:raise ValueError("TORN_ARCHIVE")
            d=zlib.decompressobj();raw=d.decompress(packed,rawlen+1)
            if len(raw)!=rawlen or not d.eof or d.unused_data or hashlib.sha256(raw).digest()!=h:
                raise ValueError("FRAME_CORRUPTION")
            if not raw.endswith(b"\n"):raise ValueError("ROW_TRUNCATED")
            for line in raw.splitlines():yield json.loads(line)
            previous=h

def row_fingerprint(table,row):
    # Exact SQLite value semantics, including original BLOB bytes and float bits.
    values=[]
    for v in row:
        if isinstance(v,bytes):values.append(["B",base64.b64encode(v).decode("ascii")])
        elif isinstance(v,float):values.append(["F",v.hex()])
        else:values.append(v)
    return canonical([table,values])+b"\n"
