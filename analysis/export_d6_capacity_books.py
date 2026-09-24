"""Export exact entry asks and exit bids for captured D6 paper signals.
Read-only against a live-growing SQLite DB; narrow indexed-style timestamp windows, no writes.
"""
import argparse,json,sqlite3,zlib
from pathlib import Path
def unpack(v):
 if isinstance(v,bytes):v=zlib.decompress(v).decode("utf-8")
 return json.loads(v)
def main():
 p=argparse.ArgumentParser();p.add_argument("db",type=Path);p.add_argument("--paper-json",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True);p.add_argument("--latency-ms",type=int,default=250);p.add_argument("--hold-ms",type=int,default=500)
 a=p.parse_args();paper=json.loads(a.paper_json.read_text(encoding="utf-8"));signals=paper.get("signals",[])
 db=sqlite3.connect(f"file:{a.db.resolve()}?mode=ro",uri=True,timeout=2)
 try:
  sid=db.execute("SELECT session_id FROM sessions ORDER BY started_at_ms DESC LIMIT 1").fetchone()[0]
  out=[]
  for s in signals:
   st=int(s["ts_ms"]);side=s["side"];entry_t=st+a.latency_ms;exit_t=entry_t+a.hold_ms
   er=db.execute("""SELECT bs.received_ts_ms,e.market_slug,bs.asks_json FROM events e JOIN book_sides bs ON bs.event_id=e.event_id
    WHERE e.session_id=? AND e.kind='BOOK' AND e.market_duration='5m' AND bs.side=? AND bs.received_ts_ms>=?
    ORDER BY bs.received_ts_ms,e.event_id LIMIT 1""",(sid,side,entry_t)).fetchone()
   if not er:continue
   ets,slug,asks=er
   xr=db.execute("""SELECT bs.received_ts_ms,bs.bids_json FROM events e JOIN book_sides bs ON bs.event_id=e.event_id
    WHERE e.session_id=? AND e.kind='BOOK' AND e.market_duration='5m' AND e.market_slug=? AND bs.side=? AND bs.received_ts_ms>=?
    ORDER BY bs.received_ts_ms,e.event_id LIMIT 1""",(sid,slug,side,exit_t)).fetchone()
   if not xr:continue
   xts,bids=xr
   out.append({"signal_ts_ms":st,"side":side,"slug":slug,"entry_ts_ms":ets,"exit_ts_ms":xts,
    "entry_asks":unpack(asks),"exit_bids":unpack(bids)})
  a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2),encoding="utf-8")
  print(json.dumps({"signals_in_snapshot":len(signals),"exported":len(out),"out":str(a.out)},indent=2))
 finally:db.close()
if __name__=="__main__":main()
