from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "c3_shadow_live.db"
OUT = ROOT / "analysis" / "c3_portfolio_results"

INITIAL_CAPITAL = 500.0
SIZES = (10.0, 20.0, 50.0)
DURATION = "5m"
DIRECTION = "DOWN->UP"
MAX_FIRST_ASK = 0.14
COOLDOWN_MS = 15_000

def load():
    with sqlite3.connect(DB) as c:
        return pd.read_sql_query("""
        SELECT id,anchor_ts_ms,hedge_ts_ms,market_slug,market_duration,direction,
               first_ask,second_ask,executable_qty,pair_cost,net_edge_005
        FROM c3_shadow_observations_v2
        WHERE market_slug IS NOT NULL AND market_slug NOT IN ('5m','15m')
          AND market_duration=? AND direction=? AND first_ask<=?
        ORDER BY anchor_ts_ms,id
        """, c, params=(DURATION,DIRECTION,MAX_FIRST_ASK))

def dedup(df):
    keep=[]
    for _,g in df.groupby("market_slug",sort=False):
        last=None
        for r in g.sort_values("anchor_ts_ms").itertuples(index=False):
            ts=int(r.anchor_ts_ms)
            if last is None or ts-last>=COOLDOWN_MS:
                keep.append(r._asdict()); last=ts
    return pd.DataFrame(keep).sort_values("anchor_ts_ms").reset_index(drop=True)

def simulate(sig, size):
    cash=INITIAL_CAPITAL; realized_equity=INITIAL_CAPITAL
    peak=INITIAL_CAPITAL; maxdd=0.0; ledger=[]; open_pos=[]
    for r in sig.itertuples(index=False):
        now=int(r.anchor_ts_ms)
        remaining=[]
        for p in open_pos:
            if p["release"]<=now:
                cash += p["return_cash"]
                realized_equity += p["pnl"]
            else:
                remaining.append(p)
        open_pos=remaining

        ask=float(r.first_ask); avail=float(r.executable_qty)
        qty=min(size/ask, avail)
        cost=qty*ask
        if cost>cash:
            qty=cash/ask; cost=qty*ask
        if qty<=0 or cost<=0: continue

        edge=float(r.net_edge_005)
        pnl=qty*edge
        cash-=cost
        open_pos.append({"release":int(r.hedge_ts_ms),
                         "return_cash":cost+pnl,"pnl":pnl})
        mtm=realized_equity + sum(p["pnl"] for p in open_pos)
        peak=max(peak,mtm); maxdd=max(maxdd,peak-mtm)
        ledger.append({"anchor_ts_ms":int(r.anchor_ts_ms),
                       "market_slug":r.market_slug,"first_ask":ask,
                       "second_ask":float(r.second_ask),"qty":qty,
                       "pair_cost":float(r.pair_cost),"net_edge_005":edge,
                       "pnl":pnl,"equity_after":mtm})
    for p in open_pos:
        cash += p["return_cash"]; realized_equity += p["pnl"]

    ld=pd.DataFrame(ledger)
    if ld.empty: raise RuntimeError("Aucun trade simulé")
    mk=ld.groupby("market_slug",as_index=False).agg(
        trades=("pnl","size"),pnl=("pnl","sum"),
        wins=("pnl",lambda x:int((x>0).sum())))
    profit=cash-INITIAL_CAPITAL
    return {
        "size":size,"capital_initial":INITIAL_CAPITAL,"capital_final":cash,
        "profit":profit,"return_pct":profit/INITIAL_CAPITAL*100,
        "trades":len(ld),"wins":int((ld.pnl>0).sum()),
        "losses":int((ld.pnl<=0).sum()),
        "win_rate_pct":float((ld.pnl>0).mean()*100),
        "max_drawdown":maxdd,
        "max_drawdown_pct":maxdd/peak*100 if peak else 0,
        "profitable_markets":int((mk.pnl>0).sum()),
        "losing_markets":int((mk.pnl<=0).sum()),
        "best_market_pnl":float(mk.pnl.max()),
        "worst_market_pnl":float(mk.pnl.min())
    },ld,mk.sort_values("pnl",ascending=False)

def main():
    print("DB:",DB)
    raw=load()
    print("RAW OBSERVATIONS:",len(raw))
    print("MARKETS WITH SIGNAL:",raw.market_slug.nunique())
    sig=dedup(raw)
    print("DEDUPLICATED SIGNALS:",len(sig))
    print("COOLDOWN: 15s\n")
    OUT.mkdir(parents=True,exist_ok=True)
    sig.to_csv(OUT/"deduplicated_signals.csv",index=False)
    summaries=[]
    for size in SIZES:
        s,ld,mk=simulate(sig,size); summaries.append(s)
        ld.to_csv(OUT/f"ledger_{int(size)}usdc.csv",index=False)
        mk.to_csv(OUT/f"markets_{int(size)}usdc.csv",index=False)
        print("="*65)
        print(f"{size:.0f} USDC / SIGNAL")
        print(f"Capital final : {s['capital_final']:.2f} USDC")
        print(f"Profit        : {s['profit']:+.2f} USDC ({s['return_pct']:+.2f}%)")
        print(f"Trades        : {s['trades']} | Win rate: {s['win_rate_pct']:.2f}%")
        print(f"Max drawdown  : {s['max_drawdown']:.2f} USDC ({s['max_drawdown_pct']:.2f}%)")
        print(f"Marchés + / - : {s['profitable_markets']} / {s['losing_markets']}")
        print(f"Best/Worst marché: {s['best_market_pnl']:+.2f} / {s['worst_market_pnl']:+.2f} USDC")
    pd.DataFrame(summaries).to_csv(OUT/"portfolio_summary.csv",index=False)
    print("\nRésultats:",OUT)

if __name__=="__main__":
    main()
