"""Single read-only readiness report. Never arms or submits."""
import inspect
import ast
import os
import time
from .production_readonly import number,fresh
from .clob_transport import LiveClobTransport


def transport_locked():
    import textwrap
    for name in ("submit_limit","submit_exit_limit","cancel_order"):
        source=inspect.getsource(getattr(LiveClobTransport,name))
        node=ast.parse(textwrap.dedent(source)).body[0]
        if not isinstance(node.body[0],ast.Raise) or "USER_APPROVAL_REQUIRED" not in ast.unparse(node.body[0]):return False
    return True


class ProductionReadinessCheck:
    def __init__(self,*,account=None,positions=None,book=None,geo=None,risk=None,local_reader=None,clock=None):
        self.sources=dict(account=account,positions=positions,book=book,geo=geo,risk=risk)
        self.local_reader=local_reader;self.clock=clock or (lambda:time.time_ns()//1_000_000)
    async def run(self):
        values={}
        for name,source in self.sources.items():
            try:
                value=source.read()
                if inspect.isawaitable(value):value=await value
                values[name]=value if isinstance(value,dict) else {}
            except Exception:values[name]={}
        now=self.clock()
        def valid(name,limit=500):
            v=values[name]
            try:return v.get("available") is True and fresh(v.get("observed_ms"),now,limit)
            except (ValueError,TypeError):return False
        a,p,b,g,r=(values[n] for n in ("account","positions","book","geo","risk"))
        def enough(field):
            try:return valid("account") and number(a.get(field))>=25
            except (ValueError,TypeError):return False
        try:
            local=self.local_reader()
            local_ok=isinstance(local,dict) and local.get("phase")=="CLOSED"
        except Exception:local_ok=False
        try:flat=valid("positions") and p.get("complete") is True and all(number(x)==0 for x in p["balances"].values())
        except (KeyError,TypeError,ValueError):flat=False
        flags={name:os.getenv(name,"false").strip().lower() for name in ("REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED")}
        checks=dict(wallet_auth=valid("account") and a.get("authenticated") is True,
            balance_usdc=enough("balance_usdc"),allowance_usdc=enough("allowance_usdc"),
            geoblock=valid("geo",60000) and g.get("blocked") is False,
            book_freshness=valid("book") and b.get("book_synced") is True,
            account_reconciliation=valid("account") and a.get("complete") is True and flat and local_ok,
            open_orders=valid("account") and a.get("complete") is True and a.get("open_order_ids")==[],
            inventory=flat,local_recovery_state=local_ok,
            session_risk=valid("risk") and r.get("allow") is True,
            transport_lock=transport_locked(),live_flags_disabled=all(v=="false" for v in flags.values()))
        return dict(status="READ_ONLY_READINESS",checks=checks,observations=values,flags=flags,
            ready_for_arm=all(checks.values()),submit_allowed=False,blockers=[k for k,v in checks.items() if not v])
