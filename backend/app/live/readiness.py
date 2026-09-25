"""Single read-only readiness report. Never arms or submits."""
import inspect
import asyncio
import ast
import os
import time
from .production_readonly import number,fresh
from .clob_transport import LiveClobTransport
from .latency_trace import measured_await


def transport_locked():
    import textwrap
    for name in ("submit_limit","submit_exit_limit","cancel_order"):
        source=inspect.getsource(getattr(LiveClobTransport,name))
        node=ast.parse(textwrap.dedent(source)).body[0]
        if not isinstance(node.body[0],ast.Raise) or "USER_APPROVAL_REQUIRED" not in ast.unparse(node.body[0]):return False
    return True


class ProductionReadinessCheck:
    def __init__(self,*,account=None,positions=None,book=None,geo=None,risk=None,local_reader=None,clock=None,collateral_unit="USDC",generation=None):
        if collateral_unit not in {"USDC","pUSD"}:raise ValueError("COLLATERAL_UNIT")
        self.generation=generation
        self.collateral_unit=collateral_unit
        self.sources=dict(account=account,positions=positions,book=book,geo=geo,risk=risk)
        self.local_reader=local_reader;self.clock=clock or (lambda:time.time_ns()//1_000_000)
    async def run(self):
        async def read_source(name,source):
            try:
                value=source.read()
                if inspect.isawaitable(value):value=await value
                return name,value if isinstance(value,dict) else {}
            except Exception:return name,{}
        values=dict(await measured_await('readiness.sources',asyncio.gather(*(read_source(n,s) for n,s in self.sources.items()))))
        try:
            local=self.local_reader()
            local_ok=isinstance(local,dict) and (local.get("phase")=="CLOSED" or (local.get("phase")=="GENESIS_RECONCILED" and local.get("integrity_verified") is True and local.get("reconciled_now") is True))
        except Exception:local_ok=False
        # Re-read the stream after awaited sources and local ledger validation.
        # Capture the evaluation clock only after these reads, never before disk I/O.
        locked=transport_locked()
        book_sample_started_ms=self.clock()
        _,values['book']=await read_source('book',self.sources['book'])
        now=self.clock()
        evaluation_cpu_started=time.thread_time_ns()
        def valid(name,limit=500):
            v=values[name]
            try:return v.get("available") is True and fresh(v.get("observed_ms"),now,limit)
            except (ValueError,TypeError):return False
        a,p,b,g,r=(values[n] for n in ("account","positions","book","geo","risk"))
        def enough(field):
            try:return valid("account") and number(a.get(field))>=25
            except (ValueError,TypeError):return False
        try:flat=valid("positions") and p.get("complete") is True and all(number(x)==0 for x in p["balances"].values())
        except (KeyError,TypeError,ValueError):flat=False
        flags={name:os.getenv(name,"false").strip().lower() for name in ("REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED")}
        balance_field="balance_usdc" if self.collateral_unit=="USDC" else "balance_collateral"
        allowance_field="allowance_usdc" if self.collateral_unit=="USDC" else "allowance_collateral"
        denomination_ok=self.collateral_unit=="USDC" or a.get("collateral_symbol")=="pUSD"
        checks=dict(wallet_auth=valid("account") and a.get("authenticated") is True,
            balance_usdc=denomination_ok and enough(balance_field),allowance_usdc=denomination_ok and enough(allowance_field),
            geoblock=valid("geo",60000) and g.get("blocked") is False,
            book_freshness=valid("book") and b.get("book_synced") is True and b.get("connected") is True,
            account_reconciliation=valid("account") and a.get("complete") is True and flat and local_ok,
            open_orders=valid("account") and a.get("complete") is True and a.get("open_order_ids")==[],
            inventory=flat,local_recovery_state=local_ok,
            session_risk=valid("risk") and r.get("allow") is True,
            transport_lock=locked,live_flags_disabled=all(v=="false" for v in flags.values()))
        if self.collateral_unit=="pUSD":
            checks["balance_pusd"]=checks.pop("balance_usdc");checks["allowance_pusd"]=checks.pop("allowance_usdc")
        generation_check=None
        if self.generation is not None:
            from .forward_readiness import validate_generation
            generation_check=validate_generation(self.generation,now)
            if not generation_check['complete']:
                for name in ('account_reconciliation','inventory','open_orders','local_recovery_state','session_risk'):
                    checks[name]=False
        try:book_time_fresh=fresh(b.get('observed_ms'),now)
        except (TypeError,ValueError):book_time_fresh=False
        book_health=(b.get('connected') is True and b.get('synchronized') is True and b.get('fresh') is True
                     and book_time_fresh and b.get('reason') in (None,'EMPTY_BOOK'))
        health_checks={k:v for k,v in checks.items() if k!='book_freshness'}
        health_checks['book_stream_health']=book_health
        system_ready=all(health_checks.values())
        market_eligible=checks['book_freshness'] and b.get('market_eligible') is True
        return dict(evaluated_ms=now,evaluation_started_ms=now,evaluation_complete_ms=self.clock(),evaluation_thread_cpu_ms=(time.thread_time_ns()-evaluation_cpu_started)/1000000,book_sample_started_ms=book_sample_started_ms,book_sample_finished_ms=now,generation=generation_check,collateral_unit=self.collateral_unit,status="READ_ONLY_READINESS",SYSTEM_READY=system_ready,MARKET_ELIGIBLE_NOW=market_eligible,
            health_checks=health_checks,operating_state="SYSTEM_BLOCKED" if not system_ready else "ELIGIBLE_BUT_LOCKED" if market_eligible else "NO_TRADE",checks=checks,observations=values,flags=flags,
            ready_for_arm=system_ready and market_eligible and all(checks.values()),submit_allowed=False,blockers=[k for k,v in checks.items() if not v])

    @staticmethod
    def qualification_snapshot(collateral,inventory,*,provenance):
        """Two-blocker phase report, explicitly not a full live-arm assessment."""
        flags={k:os.getenv(k,'false').strip().lower() for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')}
        checks={'collateral_identity_and_binding':collateral.get('conversion_allowed') is True,
                'inventory_reconciliation':inventory.get('complete') is True,
                'transport_lock':transport_locked(),'live_flags_disabled':all(v=='false' for v in flags.values())}
        return {'status':'PRODUCTION_READINESS_PHASE_CHECK','scope':'COLLATERAL_AND_INITIAL_INVENTORY_ONLY',
                'checks':checks,'blockers':[k for k,v in checks.items() if not v],
                'provenance':provenance,'flags':flags,'ready_for_arm':False,'submit_allowed':False,
                'other_live_checks':'NOT_REEVALUATED_IN_THIS_PHASE'}
