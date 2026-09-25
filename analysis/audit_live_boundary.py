"""Audit the D6 live branch for unattended readiness without submitting orders."""
import ast,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=sorted(str(p.relative_to(ROOT)).replace("\\","/")
    for folder in (ROOT/"backend/app",ROOT/"analysis")
    for p in (folder.rglob("*.py") if folder.name=="app" else folder.glob("*.py")))
FORBIDDEN={"place_limit_order","place_market_order","post_order","post_orders","cancel_order","cancel_orders","cancel_all"}

def calls(path):
 tree=ast.parse((ROOT/path).read_text(encoding="utf-8"))
 out=[]
 for n in ast.walk(tree):
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in FORBIDDEN:
   # The deterministic controller delegates cancellation to its injected transport.
   if path=="backend/app/live/execution.py" and n.func.attr=="cancel_order" and ast.unparse(n.func.value)=="self.transport":continue
   out.append({"method":n.func.attr,"line":n.lineno})
 return out

def main():
 report={"real_orders_enabled_expected":False,"files":{},"transport_boundary_only":True}
 for p in FILES:
  cs=calls(p);report["files"][p]=cs
  if cs and p!="backend/app/live/clob_transport.py":report["transport_boundary_only"]=False
 locks=[]
 tree=ast.parse((ROOT/"backend/app/live/clob_transport.py").read_text(encoding="utf-8"))
 for node in ast.walk(tree):
  if isinstance(node,ast.AsyncFunctionDef) and node.name in {"submit_limit","submit_exit_limit","cancel_order"}:
   locks.append(isinstance(node.body[0],ast.Raise) and "USER_APPROVAL_REQUIRED" in ast.unparse(node.body[0]))
 report["monetary_methods_hard_locked"]=len(locks)==3 and all(locks)
 report["files_scanned"]=len(FILES)
 report["files"]={p:cs for p,cs in report["files"].items() if cs}
 print(json.dumps(report,indent=2))
 if not report["monetary_methods_hard_locked"]:raise SystemExit(3)
 if not report["transport_boundary_only"]:raise SystemExit(2)
 print("AUDIT_OK: submission/cancel calls are isolated to clob_transport.py")
 print("NO_SUBMIT_AUDIT_ONLY")
if __name__=="__main__":main()
