"""D6 causal execution simulator for a validated D5.1 capture.

Research/paper only. Never sends orders.
"""
from __future__ import annotations
import json, sqlite3, zlib
from dataclasses import dataclass
from pathlib import Path
from .lead_lag import Tick, pct_move, value_at_or_after

@dataclass(frozen=True)
class Book:
    ts_ms:int; slug:str; expiry_ms:int; side:str; ask:float; asks:list

def _unpack(v):
    if isinstance(v,bytes): v=zlib.decompress(v).decode("utf-8")
    return json.loads(v)

def _fill(asks, budget):
    """Walk recorded asks [(price,qty),...] and return (cost, shares, vwap)."""
    remaining=float(budget); cost=shares=0.0
    for level in asks:
        price,qty=float(level[0]),float(level[1])
        if price<=0 or qty<=0: continue
        take=min(qty,remaining/price)
        cost += take*price; shares += take; remaining -= take*price
        if remaining<=1e-9: break
    return cost,shares,(cost/shares if shares else None)

def simulate(db_path, *, capital=500.0, lookback_ms=250, threshold=0.0005,
             cooldown_ms=1000, latency_ms=250, hold_ms=500, allocation=1.0):
    db=sqlite3.connect(str(db_path))
    try:
        sid,status=db.execute("SELECT session_id,status FROM sessions ORDER BY started_at_ms DESC LIMIT 1").fetchone()
        if status!="STOPPED": raise ValueError("clean STOPPED D5.1 session required")
        btc=[]
        for recv,payload in db.execute("SELECT received_ts_ms,payload_json FROM events WHERE session_id=? AND kind='BTC' ORDER BY received_ts_ms,event_id",(sid,)):
            o=_unpack(payload)
            if o.get("price") is not None: btc.append(Tick(int(recv),float(o["price"])))
        books={"UP":[],"DOWN":[]}
        q="""SELECT bs.received_ts_ms,e.market_slug,m.expiry_ts_ms,bs.side,bs.best_ask,bs.asks_json
             FROM events e JOIN book_sides bs ON bs.event_id=e.event_id
             JOIN markets m ON m.market_slug=e.market_slug
             WHERE e.session_id=? AND e.kind='BOOK' AND e.market_duration='5m'
             AND bs.best_ask IS NOT NULL ORDER BY bs.received_ts_ms,e.event_id"""
        for ts,slug,expiry,side,ask,asks in db.execute(q,(sid,)):
            books[side].append(Book(int(ts),slug,int(expiry),side,float(ask),_unpack(asks)))
        times={s:[b.ts_ms for b in arr] for s,arr in books.items()}
        def book_at(side,ts):
            from bisect import bisect_left
            arr=books[side]; i=bisect_left(times[side],ts)
            return arr[i] if i<len(arr) else None

        cash=float(capital); trades=[]; last_anchor=None
        for cur in btc:
            prior=value_at_or_after(btc,cur.ts_ms-lookback_ms)
            if prior is None or prior.ts_ms>=cur.ts_ms: continue
            move=pct_move(prior.value,cur.value)
            if abs(move)<threshold: continue
            if last_anchor is not None and cur.ts_ms-last_anchor<cooldown_ms: continue
            last_anchor=cur.ts_ms
            side="UP" if move>0 else "DOWN"
            entry=book_at(side,cur.ts_ms+latency_ms)
            if entry is None or cur.ts_ms+latency_ms>=entry.expiry_ms: continue
            exitb=book_at(side,cur.ts_ms+latency_ms+hold_ms)
            if exitb is None or exitb.slug!=entry.slug or exitb.ts_ms>=entry.expiry_ms: continue
            budget=cash*allocation
            cost,shares,vwap=_fill(entry.asks,budget)
            if not shares: continue
            # Conservative exit proxy: sell at recorded best bid from opposite-side ask complement.
            opp="DOWN" if side=="UP" else "UP"
            oppb=book_at(opp,exitb.ts_ms)
            exit_price=None if oppb is None or oppb.slug!=entry.slug else max(0.0,1.0-oppb.ask)
            if exit_price is None: continue
            proceeds=shares*exit_price
            pnl=proceeds-cost; cash += pnl
            trades.append({"signal_ts_ms":cur.ts_ms,"side":side,"btc_move":move,"slug":entry.slug,
                           "entry_ts_ms":entry.ts_ms,"entry_vwap":vwap,"shares":shares,"cost":cost,
                           "exit_ts_ms":exitb.ts_ms,"exit_price":exit_price,"proceeds":proceeds,
                           "pnl":pnl,"capital_after":cash})
        return {"contract":"D6_CAUSAL_RESEARCH_ONLY","initial_capital":capital,"final_capital":cash,
                "pnl":cash-capital,"latency_ms":latency_ms,"hold_ms":hold_ms,
                "allocation":allocation,"trade_count":len(trades),"trades":trades}
    finally: db.close()
