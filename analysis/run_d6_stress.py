"""Run a fixed D6 robustness matrix without optimizing parameters."""
import argparse,json
from pathlib import Path
from d6.execution_sim import simulate, load_execution_data

def main():
 p=argparse.ArgumentParser();p.add_argument("db",type=Path);p.add_argument("--out",type=Path)
 a=p.parse_args()
 latencies=(100,250,500,750,1000); capitals=(100.0,500.0,1000.0); allocations=(.10,.25,.50,1.0)
 data=load_execution_data(a.db)
 rows=[]
 for latency in latencies:
  for capital in capitals:
   for allocation in allocations:
    r=simulate(data=data,capital=capital,latency_ms=latency,hold_ms=500,allocation=allocation)
    rows.append({"latency_ms":latency,"capital":capital,"allocation":allocation,
                 "trade_count":r["trade_count"],"pnl":r["pnl"],
                 "return_pct":100*r["pnl"]/capital,"final_capital":r["final_capital"]})
 report={"contract":"D6_FIXED_STRESS_MATRIX_RESEARCH_ONLY","hold_ms":500,
         "latencies_ms":list(latencies),"capitals":list(capitals),"allocations":list(allocations),
         "scenario_count":len(rows),"scenarios":rows}
 s=json.dumps(report,indent=2,sort_keys=True);print(s)
 if a.out:a.out.write_text(s,encoding="utf-8")
if __name__=="__main__":main()
