"""Offline replay candidate. Streaming journal, disk duplicate index; NOT week-qualified.

Economic adapter is reused unchanged. Its state still grows with history. This
module does not advertise bounded economic state, a collector or partition access.
Scratch must be a NEW file; historical journals are opened read-only.
"""
import json, sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from .journal import validate
from .engine import ProspectiveEventAdapter
from .core import encode, safety

class DiskIds:
    def __init__(self,db): self.db=db
    def key(self,value):
        # JSON scalar equality mirrors Python sets, including True == 1 == 1.0.
        if isinstance(value,(bool,int,float)):
            n,d=value.as_integer_ratio() if isinstance(value,float) else (int(value),1)
            return encode(['number',n,d])
        if isinstance(value,str):return encode(['str',value])
        if value is None:return 'null'
        raise TypeError('unhashable event_id')
    def __contains__(self,value):
        return self.db.execute('select 1 from ids where id=?',(self.key(value),)).fetchone() is not None
    def add(self,value):self.db.execute('insert into ids values(?)',(self.key(value),))

def stream_journal(path,identity,scratch):
    safety();scratch=Path(scratch)
    # Exclusive reservation prevents accidentally modifying a previous DB.
    with scratch.open('xb'):pass
    db=sqlite3.connect(scratch)
    try:
        db.execute('pragma cache_size=-2048');db.execute('pragma temp_store=FILE')
        db.execute('create table ids(id text primary key) without rowid')
        ids=DiskIds(db);previous='0'*64;last=-1
        with Path(path).open('rb') as source:
            for sequence,line in enumerate(source):
                if not line.endswith(b'\n'):raise ValueError('TORN_JOURNAL')
                try:row=json.loads(line)
                except (ValueError,UnicodeError) as e:raise ValueError('TORN_JOURNAL') from e
                validate(row,identity,sequence,previous,ids,last)
                ids.add(row['event_id']);previous=row['event_hash'];last=row['event_ts']
                if sequence%256==255:db.commit()
                yield row
        db.commit()
    finally:db.close()

def replay_stream(path,identity,fees,scratch,*,synthetic=False):
    # No source journal records retained here and no per-event trial deep copy.
    # _apply is the same recovery transition used by the reference implementation.
    adapter=ProspectiveEventAdapter(SimpleNamespace(records=()),fees,synthetic=synthetic)
    count=0;last_hash='0'*64
    with closing(stream_journal(path,identity,scratch)) as rows:
        for row in rows:
            adapter._apply(row);count+=1;last_hash=row['event_hash']
    return adapter,dict(events=count,last_hash=last_hash,
        journal_input_streaming=True,economic_state_bounded=False)
