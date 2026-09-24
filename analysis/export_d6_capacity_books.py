"""One-pass export of entry asks / exit bids for D6 capacity analysis."""
import argparse,json,sqlite3,zlib
from pathlib import Path
def unpack(v):
 if isinstance(v,bytes):v=zlib.decompress(v).decode("utf-8")
 return json.loads(v)
def main():
 p=argparse.ArgumentParser();p.add_argument("db",type=Path);p.add_argument("--paper-json",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True);p.add_argument("--latency-ms",type=int,default=250);p.add_argument("--hold-ms",type=int,default=500)
 a=p.parse_args();paper=json.loads(a.paper_json.read_text(encoding="utf-8"));signals=paper.get("signals",[])
 targets={int(s["ts_ms"]):{"signal_ts_ms":int(s["ts_ms"]),"side":s["side"],"entry":int(s["ts_ms"])+a.latency_ms,
  "exit":int(s["ts_ms"])+a.latency_ms+a.hold_ms,"entry_row":None,"exit_row":None} for s in signals}
 lo=min(x["entry"] for x in targets.values());hi=max(x["exit"] for x in targets.values())+5000
 db=sqlite3.connect(f"file:{a.db.resolve()}?mode=ro",uri=True,timeout=2)
 try:
  sid=db.execute("SELECT session_id FROM sessions ORDER BY started_at_ms DESC LIMIT 1").fetchone()[0]
  q="""SELECT bs.received_ts_ms,e.market_slug,bs.side,bs.bids_json,bs.asks_json
       FROM events e JOIN book_sides bs ON bs.event_id=e.event_id
       WHERE e.session_id=? AND e.kind='BOOK' AND e.market_duration='5m'
         AND bs.received_ts_ms BETWEEN ? AND ?
       ORDER BY bs.received_ts_ms,e.event_id"""
  seen=0
  for ts,slug,side,bids,asks in db.execute(q,(sid,lo,hi)):
   ts=int(ts);seen+=1
   for x in targets.values():
    if side!=x["side"]:continue
    if x["entry_row"] is None and ts>=x["entry"]:
     x["entry_row"]=(ts,slug,asks)
    if x["entry_row"] is not None and x["exit_row"] is None and slug==x["entry_row"][1] and ts>=x["exit"]:
     x["exit_row"]=(ts,bids)
   if seen%100000==0:print("scanned",seen,"book sides",flush=True)
  out=[]
  for x in targets.values():
   if not x["entry_row"] or not x["exit_row"]:continue
   ets,slug,asks=x["entry_row"];xts,bids=x["exit_row"]
   out.append({"signal_ts_ms":x["signal_ts_ms"],"side":x["side"],"slug":slug,
    "entry_ts_ms":ets,"exit_ts_ms":xts,"entry_asks":unpack(asks),"exit_bids":unpack(bids)})
  a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2),encoding="utf-8")
  print(json.dumps({"signals_in_snapshot":len(signals),"exported":len(out),"scanned_book_sides":seen,"out":str(a.out)},indent=2))
 finally:db.close()
if __name__=="__main__":main()
