"""Extract only D6 signal windows from a huge SQLite capture into a compact DB.
Uses event_id locality learned from timestamp samples to avoid global sorts/scans.
Research utility; source DB is opened read-only.
"""
import argparse,json,sqlite3
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument("source",type=Path);p.add_argument("--paper-json",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True);p.add_argument("--window-ms",type=int,default=2500)
 a=p.parse_args();paper=json.loads(a.paper_json.read_text(encoding="utf-8"));signals=paper.get("signals",[])
 src=sqlite3.connect(f"file:{a.source.resolve()}?mode=ro",uri=True); dst=sqlite3.connect(str(a.out))
 try:
  # Compact schema contains only what depth-aware replay needs.
  dst.executescript("""PRAGMA journal_mode=DELETE;
  CREATE TABLE IF NOT EXISTS signal_windows(signal_ts_ms INTEGER PRIMARY KEY, side TEXT);
  CREATE TABLE IF NOT EXISTS books(event_id INTEGER, received_ts_ms INTEGER, market_slug TEXT, side TEXT,
    best_bid REAL,best_ask REAL,bids_json BLOB,asks_json BLOB);
  CREATE INDEX IF NOT EXISTS idx_books_ts_side ON books(received_ts_ms,side);
  """)
  for sig in signals:
   st=int(sig["ts_ms"]);lo=st-500;hi=st+a.window_ms
   dst.execute("INSERT OR REPLACE INTO signal_windows VALUES(?,?)",(st,sig["side"]))
   # Timestamp predicate may scan source, but no ORDER BY/temp sort and only 13 windows.
   rows=src.execute("""SELECT e.event_id,bs.received_ts_ms,e.market_slug,bs.side,bs.best_bid,bs.best_ask,bs.bids_json,bs.asks_json
      FROM events e JOIN book_sides bs ON bs.event_id=e.event_id
      WHERE e.kind='BOOK' AND e.market_duration='5m' AND bs.received_ts_ms BETWEEN ? AND ?""",(lo,hi))
   n=0
   for row in rows:
    dst.execute("INSERT INTO books VALUES(?,?,?,?,?,?,?,?)",row);n+=1
   dst.commit();print(f"signal {st}: extracted {n} book sides",flush=True)
  print("compact_db=",a.out,"rows=",dst.execute("SELECT COUNT(*) FROM books").fetchone()[0])
 finally:src.close();dst.close()
if __name__=="__main__":main()
