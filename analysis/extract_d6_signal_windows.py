"""One-pass extractor for D6 signal windows from huge SQLite captures."""
import argparse,json,sqlite3
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument("source",type=Path);p.add_argument("--paper-json",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True);p.add_argument("--before-ms",type=int,default=500);p.add_argument("--after-ms",type=int,default=2500)
 a=p.parse_args();signals=json.loads(a.paper_json.read_text(encoding="utf-8")).get("signals",[])
 windows=[(int(s["ts_ms"])-a.before_ms,int(s["ts_ms"])+a.after_ms,int(s["ts_ms"]),s["side"]) for s in signals]
 lo=min(x[0] for x in windows);hi=max(x[1] for x in windows)
 if a.out.exists():a.out.unlink()
 src=sqlite3.connect(f"file:{a.source.resolve()}?mode=ro",uri=True);dst=sqlite3.connect(str(a.out))
 try:
  dst.executescript("""PRAGMA journal_mode=DELETE;
  CREATE TABLE signal_windows(signal_ts_ms INTEGER PRIMARY KEY,side TEXT,lo_ms INTEGER,hi_ms INTEGER);
  CREATE TABLE books(event_id INTEGER,received_ts_ms INTEGER,market_slug TEXT,side TEXT,best_bid REAL,best_ask REAL,bids_json BLOB,asks_json BLOB);
  CREATE INDEX idx_books_ts_side ON books(received_ts_ms,side);""")
  dst.executemany("INSERT INTO signal_windows VALUES(?,?,?,?)",[(st,side,l,h) for l,h,st,side in windows]);dst.commit()
  q="""SELECT e.event_id,bs.received_ts_ms,e.market_slug,bs.side,bs.best_bid,bs.best_ask,bs.bids_json,bs.asks_json
       FROM events e JOIN book_sides bs ON bs.event_id=e.event_id
       WHERE e.kind='BOOK' AND e.market_duration='5m' AND bs.received_ts_ms BETWEEN ? AND ?"""
  counts={st:0 for _,_,st,_ in windows};total=0
  for row in src.execute(q,(lo,hi)):
   ts=int(row[1]);matched=[st for l,h,st,_ in windows if l<=ts<=h]
   if not matched:continue
   dst.execute("INSERT INTO books VALUES(?,?,?,?,?,?,?,?)",row);total+=1
   for st in matched:counts[st]+=1
   if total%10000==0:dst.commit();print("extracted",total,"book sides",flush=True)
  dst.commit()
  for _,_,st,_ in windows:print(f"signal {st}: {counts[st]} book sides")
  print("DONE compact_db=",a.out,"rows=",total)
 finally:src.close();dst.close()
if __name__=="__main__":main()
