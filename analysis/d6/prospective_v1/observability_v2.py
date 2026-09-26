"""Explicit observation-only AST revision, NOT adopted by any live entry point.

Version OBSERVABILITY_V1_R1. Old files remain immutable; transformed executable
AST has its own SHA. No hook can resize fills or supply a decision.
"""
import ast,copy,hashlib,json

VERSION="OBSERVABILITY_V1_R1"

def observed_tree(source):
    tree=ast.parse(source)
    class Instrument(ast.NodeTransformer):
        def visit_FunctionDef(self,node):
            return self.generic_visit(node)
        def visit_AsyncFunctionDef(self,node):
            node=self.generic_visit(node)
            if node.name=="execute_signal":
                node.body.insert(0,ast.parse('_prospective_observe("ENTRY_INTENT",dict(signal_ts=signal_ts,side=side))').body[0])
            if node.name=="on_btc":
                # after nonlocal declaration, before the original first operation
                index=1 if isinstance(node.body[0],ast.Nonlocal) else 0
                node.body.insert(index,ast.parse('_prospective_observe("BTC",dict(tick=tick))').body[0])
            return node
        def visit_Expr(self,node):
            text=ast.unparse(node)
            extra=None
            if text.startswith("ledger.record_signal("):
                extra='_prospective_observe("SIGNAL",dict(signal_ts=tick.recv_ts_ms,move=move,side=side))'
            elif text.startswith("ledger.record_skip("):
                extra='_prospective_observe("SKIP",dict(payload='+ast.unparse(node.value.args[0])+'))'
            if extra:return [node,ast.parse(extra).body[0]]
            return node
        def visit_Assign(self,node):
            text=ast.unparse(node)
            before=[];after=[]
            if text=="snap = latest.get('5m')":
                after=['_prospective_observe("ENTRY_BOOK",dict(signal_ts=signal_ts,side=side,snapshot=snap))']
            elif text.startswith("cost, shares, vwap = fill("):
                before=['_prospective_observe("ENTRY_CALC",dict(signal_ts=signal_ts,side=side,portfolio=name,budget=budget))']
                after=['_prospective_observe("ENTRY_RESULT",dict(signal_ts=signal_ts,side=side,portfolio=name,cost=cost,shares=shares,vwap=vwap,slug=snap["market_slug"]))']
            elif text=="exit_snap = latest.get('5m')":
                after=['_prospective_observe("EXIT_BOOK",dict(signal_ts=signal_ts,side=side,snapshot=exit_snap))']
            elif text.startswith("proceeds, sold, exit_vwap, remaining = liquidate("):
                before=['_prospective_observe("EXIT_CALC",dict(signal_ts=signal_ts,side=side,portfolio=name,shares=shares,slug=slug))']
                after=['_prospective_observe("EXIT_RESULT",dict(signal_ts=signal_ts,side=side,portfolio=name,proceeds=proceeds,sold=sold,vwap=exit_vwap,remaining=remaining,slug=slug))']
            elif text.startswith("take = min("):
                after=['_prospective_observe("FILL_LEVEL",dict(price=p,available=q,take=take))']
            elif text.startswith("latest[duration] = snapshot"):
                after=['_prospective_observe("BOOK",dict(duration=duration,snapshot=snapshot))']
            return [ast.parse(x).body[0] for x in before]+[node]+[ast.parse(x).body[0] for x in after]
    revised=ast.fix_missing_locations(Instrument().visit(tree))
    return revised

def revision_hash(source):
    return hashlib.sha256(ast.dump(observed_tree(source),include_attributes=False).encode()).hexdigest()

def strip_observations(tree):
    class Strip(ast.NodeTransformer):
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=="_prospective_observe":
                return None
            return node
    return ast.fix_missing_locations(Strip().visit(copy.deepcopy(tree)))

class ObservationRecorder:
    """Bounded synthetic recorder; failure invalidates observation, never V1 economics."""
    def __init__(self,max_events=10000):
        self.events=[];self.max_events=max_events;self.failed=False;self.sequence=0
    def __call__(self,kind,payload):
        try:
            if self.failed:return
            if len(self.events)>=self.max_events:
                self.failed=True;return
            self.events.append({"sequence":self.sequence,"kind":kind,"payload":copy.deepcopy(payload)})
            self.sequence+=1
        except Exception:self.failed=True
