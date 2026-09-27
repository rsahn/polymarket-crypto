"""Experimental OFFLINE recovery with exact history on a new scratch SQLite DB.

No checkpoint/resume format, collector or real V1 binding. _apply is unchanged.
RAM depends on largest record, active positions/marks and largest per-token depth;
it no longer retains every historical trade, book, fill or accounting row.
Scratch is never reopened: restart always validates/replays the source again.
"""
import json
import sqlite3
from collections.abc import MutableMapping, Sequence, Set
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from .core import safety
from .engine import ProspectiveEventAdapter
from .streaming_replay import stream_journal


def pack(v):
    if isinstance(v, Decimal): return ['decimal', str(v)]
    if isinstance(v, dict): return ['dict', [[pack(k),pack(x)] for k,x in v.items()]]
    if isinstance(v, tuple): return ['tuple', [pack(x) for x in v]]
    if isinstance(v, list): return ['list', [pack(x) for x in v]]
    if v is None or isinstance(v,(str,int,float,bool)): return ['scalar',v]
    raise TypeError(type(v))


def unpack(v):
    tag,x=v
    if tag=='decimal': return Decimal(x)
    if tag=='dict': return {unpack(k):unpack(y) for k,y in x}
    if tag=='tuple': return tuple(unpack(y) for y in x)
    if tag=='list': return [unpack(y) for y in x]
    if tag=='scalar': return x
    raise ValueError('SCRATCH_TYPE')


def dumps(v): return json.dumps(pack(v),separators=(',',':'),allow_nan=False)
def loads(v): return unpack(json.loads(v))

def key(v):
    # Match Python hash-key equality, notably 1 == True == Decimal('1.0').
    if isinstance(v,(int,float,Decimal)):
        n,d=v.as_integer_ratio() if hasattr(v,'as_integer_ratio') else (int(v),1)
        return json.dumps(['number',n,d],separators=(',',':'))
    if isinstance(v,tuple): return json.dumps(['tuple',[key(x) for x in v]],separators=(',',':'))
    hash(v)
    return dumps(v)


class Store:
    def __init__(self,path):
        safety(); self.path=Path(path)
        with self.path.open('xb'): pass
        self.db=sqlite3.connect(self.path)
        self.db.execute('pragma cache_size=-2048')
        self.db.execute('pragma temp_store=FILE')
        self.db.execute('create table maps(n text,k text,original text,v text,unique(n,k))')
        self.db.execute('create table arrays(n text,i integer,v text,primary key(n,i)) without rowid')
    def close(self): self.db.close()
    def commit(self): self.db.commit()


class DiskList(Sequence):
    def __init__(self,s,n): self.s=s; self.n=n
    def __len__(self):
        return self.s.db.execute('select coalesce(max(i)+1,0) from arrays where n=?',(self.n,)).fetchone()[0]
    def append(self,v): self.s.db.execute('insert into arrays values(?,?,?)',(self.n,len(self),dumps(v)))
    def __getitem__(self,i):
        if isinstance(i,slice): return list(self)[i] # diagnostics only; not recovery
        if i<0: i+=len(self)
        r=self.s.db.execute('select v from arrays where n=? and i=?',(self.n,i)).fetchone()
        if r is None: raise IndexError(i)
        return loads(r[0])
    def __iter__(self):
        for r in self.s.db.execute('select v from arrays where n=? order by i',(self.n,)): yield loads(r[0])
    def __reversed__(self):
        for r in self.s.db.execute('select v from arrays where n=? order by i desc',(self.n,)): yield loads(r[0])


class TrackedDict(dict):
    """One-level write-through for the exact nested mappings used by _apply."""
    def __init__(self,v,save): super().__init__(v); self.save=save
    def __setitem__(self,k,v): super().__setitem__(k,v); self.save(dict(self))
    def __delitem__(self,k): super().__delitem__(k); self.save(dict(self))


class DiskMap(MutableMapping):
    def __init__(self,s,n): self.s=s; self.n=n
    def __len__(self): return self.s.db.execute('select count(*) from maps where n=?',(self.n,)).fetchone()[0]
    def __iter__(self):
        for r in self.s.db.execute('select original from maps where n=? order by rowid',(self.n,)): yield loads(r[0])
    def __getitem__(self,k):
        r=self.s.db.execute('select v from maps where n=? and k=?',(self.n,key(k))).fetchone()
        if r is None: raise KeyError(k)
        v=loads(r[0])
        return TrackedDict(v,lambda x:self.__setitem__(k,x)) if isinstance(v,dict) else v
    def __setitem__(self,k,v):
        self.s.db.execute('insert into maps values(?,?,?,?) on conflict(n,k) do update set v=excluded.v',
                         (self.n,key(k),dumps(k),dumps(v)))
    def __delitem__(self,k):
        c=self.s.db.execute('delete from maps where n=? and k=?',(self.n,key(k)))
        if c.rowcount!=1: raise KeyError(k)


class DiskSet(Set):
    def __init__(self,s,n): self.m=DiskMap(s,n)
    def __contains__(self,k): return k in self.m
    def __iter__(self): return iter(self.m)
    def __len__(self): return len(self.m)
    def add(self,k): self.m[k]=True


class DiskBooks(MutableMapping):
    def __init__(self,s): self.s=s; self.m=DiskMap(s,'book_tokens')
    def __len__(self): return len(self.m)
    def __iter__(self): return iter(self.m)
    def __getitem__(self,k): return DiskList(self.s,self.m[k])
    def __setitem__(self,k,v):
        if k in self.m or v!=[]: raise ValueError('BOOK_HISTORY_REPLACEMENT_FORBIDDEN')
        self.m[k]='book:'+key(k)
    def __delitem__(self,k): raise ValueError('BOOK_HISTORY_REMOVAL_FORBIDDEN')
    def setdefault(self,k,default=None):
        if k not in self.m: self[k]=default
        return self[k]


class OfflineDiskAdapter(ProspectiveEventAdapter):
    def observe(self,event): raise ValueError('OFFLINE_RECOVERY_ONLY')


def adapter_on_disk(store,fees,synthetic):
    a=OfflineDiskAdapter(SimpleNamespace(records=()),fees,synthetic=synthetic)
    a.states=DiskMap(store,'states'); a.accounting=DiskList(store,'accounting')
    a.fee_annotations=DiskSet(store,'fee_annotations')
    for name in ('reservations','positions'): setattr(a.ledger,name,DiskMap(store,'ledger_'+name))
    a.ledger.ids=DiskSet(store,'ledger_ids'); a.ledger.events=DiskList(store,'ledger_events')
    a.tape.ids=DiskSet(store,'book_ids'); a.tape.depth=DiskMap(store,'depth'); a.tape.books=DiskBooks(store)
    return a


def replay_disk(path,identity,fees,scratch,ids_scratch,*,synthetic=False,progress=None):
    """Return (adapter, metadata, store). Caller must close store; never use observe()."""
    store=Store(scratch)
    try:
        a=adapter_on_disk(store,fees,synthetic); count=0; last_hash='0'*64
        with closing(stream_journal(path,identity,ids_scratch)) as rows:
            for row in rows:
                a._apply(row); count+=1; last_hash=row['event_hash']
                if count%256==0: store.commit()
                if progress is not None and count%10000==0: progress(count,a,store)
        store.commit()
        return a,dict(events=count,last_sequence=count-1,last_hash=last_hash,identity=dict(identity),
                      historical_containers_on_disk=True,protocol_memory_bound_proven=False),store
    except BaseException:
        store.close(); raise


def materialize(a):
    """Only small-fixture comparison. Explicitly O(N); never called by stress/recovery."""
    return dict(mark=a.ledger.mark(a.marks),fills=list(a.ledger.events),states=dict(a.states),
                accounting=list(a.accounting),books={t:list(v) for t,v in a.tape.books.items()},
                depth=[[t,s,str(p),str(v),str(r)] for (t,s),levels in sorted(a.tape.depth.items())
                       for p,(v,r) in sorted(levels.items())],ended=a.ended,fee_annotations=sorted(a.fee_annotations))
