import argparse,json
from pathlib import Path
from d6.execution_sim import simulate
def main():
 p=argparse.ArgumentParser();p.add_argument("db",type=Path);p.add_argument("--capital",type=float,default=500)
 p.add_argument("--latency-ms",type=int,default=250);p.add_argument("--hold-ms",type=int,default=500)
 p.add_argument("--allocation",type=float,default=1.0);p.add_argument("--out",type=Path)
 a=p.parse_args();r=simulate(a.db,capital=a.capital,latency_ms=a.latency_ms,hold_ms=a.hold_ms,allocation=a.allocation)
 s=json.dumps(r,indent=2,sort_keys=True);print(s)
 if a.out:a.out.write_text(s,encoding="utf-8")
if __name__=="__main__":main()
