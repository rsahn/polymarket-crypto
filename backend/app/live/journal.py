"""Append-only JSONL audit journal for shadow/live execution."""
import json,time,uuid
from pathlib import Path

class LiveJournal:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
    def signal_id(self,signal_ts_ms,market_slug,side):
        return f"{signal_ts_ms}:{market_slug}:{side}"
    def append(self,event_type,signal_id,**data):
        row={"event_id":uuid.uuid4().hex,"event_type":event_type,"signal_id":signal_id,
             "logged_ts_ms":int(time.time()*1000),**data}
        with self.path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
            f.flush()
        return row
    def events(self,signal_id=None):
        if not self.path.exists():return []
        rows=[json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
        return rows if signal_id is None else [x for x in rows if x.get("signal_id")==signal_id]
