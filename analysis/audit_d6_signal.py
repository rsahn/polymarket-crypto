"""Audit one D6 paper signal against immutable rows already committed to the live DB."""
import argparse,json,sqlite3,zlib
from pathlib import Path

def unpack(v):
 if isinstance(v,bytes):v=zlib.decompress(v).decode("utf-8")
 return json.loads(v)

def main():
 p=argparse.ArgumentParser();p.add_argument("db",type=Path);p.add_argument("--signal-ts-ms",type=int,required=True)
 p.add_argument("--slug",required=True);p.add_argument("--side",choices=["UP","DOWN"],required=True);p.add_argument("--out",type=Path)
 a=p.parse_args();db=sqlite3.connect(f"file:{a.db.resolve()}?mode=ro",uri=True)
 try:
  sid=db.execute("SELECT session_id FROM sessions ORDER BY started_at_ms DESC LIMIT 1").fetchone()[0]
  offsets=(-250,0,50,100,250,750,1000);rows=[]
  for off in offsets:
   target=a.signal_ts_ms+off
   row=db.execute("""SELECT bs.received_ts_ms,bs.best_bid,bs.best_ask,bs.bids_json,bs.asks_json,e.generation
    FROM events e JOIN book_sides bs ON bs.event_id=e.event_id
    WHERE e.session_id=? AND e.kind='BOOK' AND e.market_slug=? AND bs.side=? AND bs.received_ts_ms>=?
    ORDER BY bs.received_ts_ms,e.event_id LIMIT 1""",(sid,a.slug,a.side,target)).fetchone()
   if row:
    ts,bid,ask,bids,asks,gen=row
    rows.append({"offset_ms":off,"target_ts_ms":target,"book_ts_ms":ts,"book_delay_ms":ts-target,
     "best_bid":bid,"best_ask":ask,"generation":gen,"bids":unpack(bids),"asks":unpack(asks)})
   else:rows.append({"offset_ms":off,"target_ts_ms":target,"missing":True})
  rejects=db.execute("""SELECT kind,received_ts_ms,payload_json FROM events
   WHERE session_id=? AND received_ts_ms BETWEEN ? AND ? AND kind='REJECT'
   ORDER BY received_ts_ms""",(sid,a.signal_ts_ms-1000,a.signal_ts_ms+2000)).fetchall()
  controls=db.execute("""SELECT kind,received_ts_ms,market_slug,generation,payload_json FROM events
   WHERE session_id=? AND received_ts_ms BETWEEN ? AND ? AND kind IN ('ACTIVATE','INVALIDATE','ROTATION','RECONNECT','WS_ERROR')
   ORDER BY received_ts_ms""",(sid,a.signal_ts_ms-2000,a.signal_ts_ms+2000)).fetchall()
  # Recompute the exact 100-unit entry from the first accepted BOOK at T+250.
  entry=next((x for x in rows if x.get("offset_ms")==250 and not x.get("missing")),None)
  fill100=None
  if entry:
   rem=100.0;cost=shares=0.0;levels=[]
   for level in entry["asks"]:
    price,qty=float(level[0]),float(level[1])
    if price<=0 or qty<=0: continue
    take=min(qty,rem/price);spent=take*price
    if take>0: levels.append({"price":price,"available_qty":qty,"taken_qty":take,"spent":spent})
    cost+=spent;shares+=take;rem-=spent
    if rem<=1e-9: break
   fill100={"book_ts_ms":entry["book_ts_ms"],"generation":entry["generation"],"best_ask":entry["best_ask"],
    "cost":cost,"shares":shares,"vwap":(cost/shares if shares else None),"unfilled_budget":rem,"levels":levels}
  report={"contract":"D6_SIGNAL_AUDIT","session_id":sid,"signal_ts_ms":a.signal_ts_ms,"slug":a.slug,"side":a.side,
   "books":rows,"recomputed_entry_100":fill100,"rejects":[{"kind":k,"ts_ms":t,"payload":unpack(v)} for k,t,v in rejects],
   "controls":[{"kind":k,"ts_ms":t,"slug":s,"generation":g,"payload":unpack(v) if v else None} for k,t,s,g,v in controls]}
  s=json.dumps(report,indent=2,sort_keys=True);print(s)
  if a.out:a.out.write_text(s,encoding="utf-8")
 finally:db.close()
if __name__=="__main__":main()
