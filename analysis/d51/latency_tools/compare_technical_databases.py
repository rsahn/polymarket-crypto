"""Exact readonly comparison of technical fixture DBs, never quality validation."""
import argparse,json,pathlib,sqlite3,time

def compare(left,right,output):
    paths=[pathlib.Path(x).resolve() for x in (left,right)]
    if any(p.name!='technical_only.db' for p in paths):raise ValueError('Technical fixture DBs only')
    before=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    dbs=[sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True) for p in paths]
    counts={};started=time.monotonic()
    try:
        for db in dbs:db.execute('PRAGMA query_only=ON')
        for table in ('events','book_sides','anchors','markets'):
            cols=[[r[1] for r in db.execute('PRAGMA table_info('+table+')')] for db in dbs]
            assert cols[0]==cols[1],table
            selected=[c for c in cols[0] if c not in ('session_id','closed_at_ms')]
            query='SELECT '+','.join('"'+c+'"' for c in selected)+' FROM '+table+' ORDER BY rowid'
            streams=[db.execute(query) for db in dbs];n=0
            while True:
                a,b=[cur.fetchone() for cur in streams]
                assert a==b,(table,n)
                if a is None:break
                n+=1
            counts[table]=n
    finally:
        for db in dbs:db.close()
    assert before==[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    r=dict(status='PASS',technical_only=True,rows_equal=counts,excluded_columns=['session_id','closed_at_ms'],payloads_depths_timestamps_byte_identical=True,source_stats_unchanged=True,seconds=time.monotonic()-started)
    with pathlib.Path(output).open('x') as f:json.dump(r,f,indent=2)
    print(json.dumps(r))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('left');a.add_argument('right');a.add_argument('output');v=a.parse_args();compare(v.left,v.right,v.output)
