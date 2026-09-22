"""D6 V1 live paper engine. SHADOW/PAPER ONLY: never submits real orders."""
from __future__ import annotations
import asyncio,json,time
from dataclasses import dataclass,asdict
from pathlib import Path

@dataclass
class Portfolio:
    name:str; capital:float=500.0; pnl:float=0.0; trades:int=0; peak:float=500.0; max_drawdown:float=0.0
    def mark(self,pnl):
        self.pnl+=pnl; self.capital+=pnl; self.trades+=1; self.peak=max(self.peak,self.capital)
        self.max_drawdown=max(self.max_drawdown,self.peak-self.capital)

class PaperLedger:
    """One signal -> parallel virtual sizings, with persistent snapshots."""
    def __init__(self,out_dir,initial=500.0,snapshot_hours=10):
        self.out=Path(out_dir);self.out.mkdir(parents=True,exist_ok=True)
        self.snapshot_seconds=snapshot_hours*3600
        self.started_ms=int(time.time()*1000);self.last_snapshot=time.monotonic()
        self.portfolios={k:Portfolio(k,initial,peak=initial) for k in ("fixed_25","fixed_50","fixed_100","dynamic_depth")}
        self.signals=[];self.fills=[];self.errors=[]
    def sizes(self,available_eur):
        return {"fixed_25":min(25,available_eur),"fixed_50":min(50,available_eur),
                "fixed_100":min(100,available_eur),"dynamic_depth":max(0,min(100,available_eur*.25))}
    def record_signal(self,row): self.signals.append(dict(row))
    def record_skip(self,row):
        self.fills.append({"portfolio":None,"status":"SKIP",**dict(row)})
    def record_fill(self,name,row,pnl):
        self.portfolios[name].mark(float(pnl));self.fills.append({"portfolio":name,**row,"pnl":float(pnl)})
    def state(self):
        return {"contract":"D6_V1_PAPER_ONLY","started_ms":self.started_ms,"updated_ms":int(time.time()*1000),
                "signal_count":len(self.signals),"fill_count":len(self.fills),
                "portfolios":{k:asdict(v) for k,v in self.portfolios.items()},
                "signals":self.signals,"fills":self.fills,"errors":self.errors}
    def snapshot(self,force=False):
        if not force and time.monotonic()-self.last_snapshot<self.snapshot_seconds:return None
        stamp=time.strftime("%Y%m%d_%H%M%S")
        p=self.out/f"paper_{stamp}.json";p.write_text(json.dumps(self.state(),indent=2,sort_keys=True),encoding="utf-8")
        latest=self.out/"LATEST.json";latest.write_text(json.dumps(self.state(),indent=2,sort_keys=True),encoding="utf-8")
        self.last_snapshot=time.monotonic();return p

V1={"btc_threshold_bps":5.0,"btc_lookback_ms":250,"cooldown_ms":1000,"market":"5m",
    "parallel_sizes_eur":[25,50,100],"dynamic_depth_fraction":0.25,"dynamic_cap_eur":100,
    "snapshot_hours":10,"mode":"PAPER","real_orders":False}
