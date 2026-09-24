"""Audit the D6 live branch for unattended readiness without submitting orders."""
import ast,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=[
 "backend/app/live/clob_staged.py",
 "backend/app/live/clob_transport.py",
 "backend/app/live/real_scaffold.py",
 "analysis/run_d6_paper_live.py",
]
FORBIDDEN={"place_limit_order","place_market_order","post_order","post_orders","cancel_order","cancel_orders","cancel_all"}

def calls(path):
 tree=ast.parse((ROOT/path).read_text(encoding="utf-8"))
 out=[]
 for n in ast.walk(tree):
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in FORBIDDEN:
   out.append({"method":n.func.attr,"line":n.lineno})
 return out

def main():
 report={"real_orders_enabled_expected":False,"files":{},"transport_boundary_only":True}
 for p in FILES:
  cs=calls(p);report["files"][p]=cs
  if cs and p!="backend/app/live/clob_transport.py":report["transport_boundary_only"]=False
 print(json.dumps(report,indent=2))
 if not report["transport_boundary_only"]:raise SystemExit(2)
 print("AUDIT_OK: submission/cancel calls are isolated to clob_transport.py")
 print("NO_SUBMIT_AUDIT_ONLY")
if __name__=="__main__":main()
