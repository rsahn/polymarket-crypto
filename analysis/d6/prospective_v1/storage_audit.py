"""Read-only physical/logical storage accounting; never opens source writable."""
import collections,json,sqlite3,struct
from contextlib import closing
from pathlib import Path

def readonly(path):
    p=Path(path).resolve()
    for suffix in ("-wal","-journal"):
        side=Path(str(p)+suffix)
        if side.exists() and side.stat().st_size: raise ValueError("SOURCE_NOT_QUIESCENT")
    c=sqlite3.connect(p.as_uri()+"?mode=ro&immutable=1",uri=True)
    c.execute("PRAGMA query_only=ON");c.execute("PRAGMA cache_size=-16384")
    return c

def physical_pages(path):
    """SQLite fileformat.html btree/overflow walk; no dbstat dependency."""
    p=Path(path)
    with closing(readonly(p)) as c:
        roots=c.execute("select name,rootpage from sqlite_master where rootpage>0").fetchall()
    roots=[("sqlite_schema",1)]+roots
    with p.open("rb") as f:
        header=f.read(100)
        if header[:16]!=b"SQLite format 3\0":raise ValueError("NOT_SQLITE")
        size=int.from_bytes(header[16:18],"big");size=65536 if size==1 else size
        usable=size-header[20];total=p.stat().st_size//size
        if int.from_bytes(header[52:56],"big"):raise ValueError("AUTOVACUUM_NOT_SUPPORTED")
        seen=bytearray(total+1);counts=collections.Counter()
        def page(n,owner):
            if not 1<=n<=total or seen[n]:raise ValueError("PAGE_OWNERSHIP_CONFLICT")
            seen[n]=1;counts[owner]+=1;f.seek((n-1)*size);b=f.read(size)
            if len(b)!=size:raise ValueError("SHORT_PAGE")
            return b
        def varint(b,i):
            v=0
            for j in range(9):
                x=b[i];i+=1
                if j==8:return (v<<8)|x,i
                v=(v<<7)|(x&127)
                if x<128:return v,i
            raise AssertionError()
        def u32(b,i):return int.from_bytes(b[i:i+4],"big")
        for owner,root in roots:
            stack=[root]
            while stack:
                n=stack.pop();b=page(n,owner);o=100 if n==1 else 0;kind=b[o]
                if kind not in (2,5,10,13):raise ValueError("NOT_BTREE")
                count=int.from_bytes(b[o+3:o+5],"big");interior=kind in (2,5)
                if interior:stack.append(u32(b,o+8))
                base=o+(12 if interior else 8)
                for k in range(count):
                    at=int.from_bytes(b[base+2*k:base+2*k+2],"big")
                    if interior:stack.append(u32(b,at));at+=4
                    if kind==5:continue
                    length,at=varint(b,at)
                    if kind==13:_,at=varint(b,at)
                    maximum=usable-35 if kind==13 else (usable-12)*64//255-23
                    if length>maximum:
                        minimum=(usable-12)*32//255-23
                        local=minimum+(length-minimum)%(usable-4)
                        if local>maximum:local=minimum
                        link=u32(b,at+local)
                        while link:
                            overflow=page(link,owner);link=u32(overflow,0)
        trunk=u32(header,32)
        while trunk:
            b=page(trunk,"FREELIST");num=u32(b,4)
            for i in range(num):page(u32(b,8+4*i),"FREELIST")
            trunk=u32(b,0)
        lock_page=0x40000000//size+1
        if lock_page<=total and not seen[lock_page]:
            seen[lock_page]=1;counts["SQLITE_BYTE_LOCK_PAGE"]+=1
        counts["UNATTRIBUTED"]=total-sum(counts.values())
        return {"page_size":size,"pages":total,"bytes":p.stat().st_size,
                "by_object":{k:v*size for k,v in counts.items()}}

def breakdown(path,side_directory):
    p=Path(path); before=(p.stat().st_size,p.stat().st_mtime_ns)
    physical=physical_pages(p)
    if physical["by_object"]["UNATTRIBUTED"]!=0:raise ValueError("UNATTRIBUTED_PAGES")
    c=readonly(p)
    try:
        event_rows=c.execute("select kind,market_duration,count(*),sum(length(payload_json)) from events group by kind,market_duration").fetchall()
        sides=c.execute("select count(*),sum(length(bids_json)),sum(length(asks_json)) from book_sides").fetchone()
        anchors=c.execute("select count(*),coalesce(sum(length(features_json)),0) from anchors").fetchone()
        tables={name:c.execute('select count(*) from "'+name+'"').fetchone()[0]
                for name, in c.execute("select name from sqlite_master where type='table'")}
        # Consecutive equal depth per token, byte-exact equality, not sampled.
        prior={}; duplicates=duplicate_bytes=rows=0
        for token,bids,asks in c.execute("select token_id,bids_json,asks_json from book_sides order by event_id,side"):
            rows+=1; value=(bids,asks)
            if prior.get(token)==value:
                duplicates+=1;duplicate_bytes+=len(bids)+len(asks)
            prior[token]=value
        files=[{"path":str(f),"bytes":f.stat().st_size} for f in Path(side_directory).rglob("*") if f.is_file()]
    finally:c.close()
    after=(p.stat().st_size,p.stat().st_mtime_ns)
    if before!=after:raise ValueError("SOURCE_CHANGED")
    logical={"event_payload_by_kind_duration":[{"kind":k,"duration":d,"events":n,"stored_payload_bytes":s}
        for k,d,n,s in event_rows],"book_side_count":sides[0],"bid_depth_bytes":sides[1],
        "ask_depth_bytes":sides[2],"anchors":anchors[0],"anchor_features_bytes":anchors[1],
        "adjacent_duplicate_depth_rows":duplicates,"adjacent_duplicate_depth_bytes":duplicate_bytes,
        "duplicate_scope":"per token, consecutive byte-identical stored bids+asks; subset of depth, NOT additive"}
    return {"source":str(p),"source_stat_unchanged":True,"physical":physical,"table_counts":tables,
        "logical":logical,"side_files":files,
        "source_mutation":False,"economic_metrics_computed":False}
