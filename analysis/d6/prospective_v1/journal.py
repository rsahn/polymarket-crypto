"""Single-writer, append-only journal. Torn/ambiguous writes invalidate the run.

fsync is an OS durability request, not certification of the physical disk.
No truncation, repair, retry or inferred events. Recovery replays complete records.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from .core import digest, encode, safety

KINDS = set("""SIGNAL ENTRY_INTENT ENTRY_BOOK ENTRY_FILL ENTRY_PARTIAL_FILL
ENTRY_NO_FILL EXIT_INTENT EXIT_BOOK EXIT_FILL EXIT_PARTIAL_FILL EXIT_NO_FILL
POSITION_OPEN POSITION_RESIDUAL POSITION_SETTLED FEE CASH_RESERVED CASH_RELEASED
MARK SESSION_END""".split())
IDENTITY_FIELDS = ("strategy_hash","runner_hash","dataset_session_id","partition")
FIELDS = set("""event_id kind market_id token_id direction source_ts recv_ts
decision_ts event_ts book_ts price qty notional fee""".split())

def validate(record, identity, sequence, previous, ids, last_ts):
    if not FIELDS.issubset(record) or record["kind"] not in KINDS:
        raise ValueError("EVENT_SCHEMA")
    if any(record.get(k)!=identity[k] for k in IDENTITY_FIELDS):
        raise ValueError("IDENTITY_OR_PARTITION_MISMATCH")
    if record.get("sequence")!=sequence: raise ValueError("SEQUENCE_GAP")
    if record.get("previous_event_hash")!=previous: raise ValueError("HASH_CHAIN_BREAK")
    payload={k:v for k,v in record.items() if k!="event_hash"}
    if record.get("event_hash")!=digest(payload): raise ValueError("EVENT_HASH_MISMATCH")
    if not record["event_id"] or record["event_id"] in ids: raise ValueError("DUPLICATE_EVENT")
    times=[record[k] for k in ("source_ts","recv_ts","decision_ts","event_ts")]
    if any(type(t)!=int or t<0 for t in times) or times!=sorted(times):
        raise ValueError("FUTURE_TIMESTAMP_OR_CLOCK_ORDER")
    if times[-1]<last_ts: raise ValueError("TIMESTAMP_REGRESSION")
    if times[-1]>time.time_ns()//1_000_000: raise ValueError("FUTURE_TIMESTAMP")
    book=record["book_ts"]
    if book is not None and (type(book)!=int or not 0<=book<=times[2]):
        raise ValueError("FUTURE_BOOK_TIMESTAMP")

def read_journal(path, identity):
    records=[]; ids=set(); previous="0"*64; last=-1
    with Path(path).open("rb") as f:
        for line in f:
            if not line.endswith(b"\n"): raise ValueError("TORN_JOURNAL")
            try: row=json.loads(line)
            except (ValueError,UnicodeError) as e: raise ValueError("TORN_JOURNAL") from e
            validate(row,identity,len(records),previous,ids,last)
            records.append(row); ids.add(row["event_id"])
            previous=row["event_hash"]; last=row["event_ts"]
    return records

class DurableEventJournal:
    def __init__(self,path,identity):
        safety()
        self.path=Path(path); self.identity=dict(identity)
        if set(IDENTITY_FIELDS)-set(identity): raise ValueError("MISSING_IDENTITY")
        if identity["partition"] not in ("TRAIN","VALIDATION","OOS"):
            raise ValueError("INVALID_PARTITION")
        self.poisoned=False; self.closed=False; self.file=None; self.lock=None
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            # OS advisory lock survives no process crash. Sidecar contents are not a lease.
            self.lock=self.path.with_suffix(self.path.suffix+".lock").open("a+b")
            if self.lock.seek(0,2)==0: self.lock.write(b"0"); self.lock.flush()
            self.lock.seek(0)
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            if self.path.with_suffix(".SEALED.json").exists(): raise ValueError("PARTITION_SEALED")
            self.records=read_journal(self.path,self.identity) if self.path.exists() else []
            self.ids={e["event_id"] for e in self.records}
            self.file=self.path.open("ab",buffering=0)
        except BaseException:
            self.close()
            raise
    def preview(self,event):
        if self.poisoned or self.closed: raise ValueError("JOURNAL_POISONED_OR_CLOSED")
        if self.path.with_suffix(".SEALED.json").exists(): raise ValueError("PARTITION_SEALED")
        if any(k in event and event[k]!=v for k,v in self.identity.items()):
            raise ValueError("IDENTITY_OR_PARTITION_MISMATCH")
        if {"sequence","event_hash","previous_event_hash"} & event.keys():
            raise ValueError("RESERVED_JOURNAL_FIELDS")
        e=json.loads(encode(event)); e.update(self.identity)
        e["sequence"]=len(self.records)
        e["previous_event_hash"]=self.records[-1]["event_hash"] if self.records else "0"*64
        e["event_hash"]=digest(e)
        validate(e,self.identity,len(self.records),e["previous_event_hash"],self.ids,
                 self.records[-1]["event_ts"] if self.records else -1)
        return e
    def append(self,event):
        safety(); e=self.preview(event)
        data=(encode(e)+"\n").encode("utf-8")
        try:
            if self.file.write(data)!=len(data): raise OSError("PARTIAL_WRITE")
            self.file.flush(); os.fsync(self.file.fileno())
        except BaseException:
            self.poisoned=True
            raise
        # Only acknowledge/apply after successful fsync.
        self.records.append(e); self.ids.add(e["event_id"])
        return json.loads(encode(e))
    def close(self):
        if self.file is not None: self.file.close(); self.file=None
        if self.lock is not None: self.lock.close(); self.lock=None
        self.closed=True
