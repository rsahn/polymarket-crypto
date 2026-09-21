from __future__ import annotations

import re
import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "c3_shadow_live.db"
OUT = ROOT / "analysis" / "c3_portfolio_v4_results"

INITIAL_CAPITAL = 500.0
LEG1_BUDGETS = (10.0, 20.0, 50.0)

# Règle figée D3
DURATION = "5m"
DIRECTION = "DOWN->UP"
MAX_FIRST_ASK = 0.14
COOLDOWN_MS = 15_000
FRICTION_PER_PAIR = 0.005
MARKET_LENGTH_MS = 5 * 60 * 1000


def market_end_ms(slug: str) -> int:
    m = re.search(r"-(\d+)$", str(slug))
    if not m:
        raise ValueError(f"Timestamp absent du slug: {slug}")
    return int(m.group(1)) * 1000 + MARKET_LENGTH_MS


def load_signals():
    with sqlite3.connect(DB) as db:
        return pd.read_sql_query(
            """
            SELECT id,anchor_ts_ms,hedge_ts_ms,market_slug,market_duration,direction,
                   first_bid,first_ask,first_bid_qty,first_ask_qty,
                   second_ask,second_ask_qty,executable_qty,pair_cost,gross_edge
            FROM c3_shadow_observations_v2
            WHERE market_slug IS NOT NULL
              AND market_slug NOT IN ('5m','15m')
              AND market_duration=?
              AND direction=?
              AND first_ask<=?
            ORDER BY anchor_ts_ms,id
            """,
            db, params=(DURATION, DIRECTION, MAX_FIRST_ASK)
        )


def dedup(df):
    selected=[]
    for _,g in df.groupby("market_slug",sort=False):
        last=None
        for r in g.sort_values("anchor_ts_ms").itertuples(index=False):
            ts=int(r.anchor_ts_ms)
            if last is None or ts-last>=COOLDOWN_MS:
                d=r._asdict()
                d["market_end_ms"]=market_end_ms(r.market_slug)
                selected.append(d)
                last=ts
    return pd.DataFrame(selected).sort_values("anchor_ts_ms").reset_index(drop=True)


def settle_pairs(open_pairs,cash,now,ledger):
    rem=[]
    for p in open_pairs:
        if p["market_end_ms"]<=now:
            payout=p["qty"]
            cash+=payout
            p["payout"]=payout
            p["pnl"]=payout-p["total_cost"]
            ledger.append(p)
        else:
            rem.append(p)
    return rem,cash


def simulate(sig,budget):
    cash=INITIAL_CAPITAL
    pairs=[]
    ledger=[]
    rejected_no_cash=0
    reduced=0
    failed=0
    exit_leg1=0
    peak=INITIAL_CAPITAL
    maxdd=0.0

    for r in sig.itertuples(index=False):
        now=int(r.anchor_ts_ms)
        pairs,cash=settle_pairs(pairs,cash,now,ledger)

        p1=float(r.first_ask)
        p2=float(r.second_ask)
        q1book=float(r.first_ask_qty)
        q2book=float(r.second_ask_qty)

        q1=min(budget/p1,q1book,cash/p1)
        if q1<=0:
            rejected_no_cash+=1
            continue

        original_q1=q1
        original_leg1_cost=q1*p1
        cash-=original_leg1_cost

        # Combien peut réellement être hedgé avec LEG2 ?
        qcash=cash/(p2+FRICTION_PER_PAIR) if p2+FRICTION_PER_PAIR>0 else 0
        qpair=min(q1,q2book,qcash)

        # Partie non hedgée : sortie immédiate au bid T0 comme approximation
        # conservatrice disponible dans notre dataset. Pas de remboursement magique.
        qunhedged=q1-qpair
        if qunhedged>1e-12:
            failed += int(qpair<=1e-12)
            reduced += int(qpair>1e-12)
            bid=float(r.first_bid) if r.first_bid is not None else 0.0
            bid_qty=float(r.first_bid_qty or 0.0)
            qexit=min(qunhedged,bid_qty)
            if qexit>0:
                cash += qexit*bid
                exit_leg1 += 1

            # Si le carnet T0 ne permet même pas la sortie complète, on valorise
            # le reliquat à zéro : hypothèse volontairement sévère.
            # Son coût reste donc perdu dans le cash déjà débité.

        if qpair>1e-12:
            # Remboursement comptable du coût LEG1 de la portion non pairée
            # N'EST PAS effectué. La portion sortie a été créditée au bid ci-dessus.
            leg1_pair_cost=qpair*p1
            leg2_cost=qpair*p2
            friction=qpair*FRICTION_PER_PAIR
            cash-=leg2_cost+friction

            if cash < -1e-7:
                raise RuntimeError("Invariant cash négatif")

            pairs.append({
                "anchor_ts_ms":int(r.anchor_ts_ms),
                "hedge_ts_ms":int(r.hedge_ts_ms),
                "market_end_ms":int(r.market_end_ms),
                "market_slug":r.market_slug,
                "leg1_budget":budget,
                "first_ask":p1,
                "second_ask":p2,
                "qty":qpair,
                "leg1_cost":leg1_pair_cost,
                "leg2_cost":leg2_cost,
                "friction":friction,
                "total_cost":leg1_pair_cost+leg2_cost+friction,
                "pair_cost_net":p1+p2+FRICTION_PER_PAIR,
            })

        equity=cash+sum(p["qty"] for p in pairs)
        peak=max(peak,equity)
        maxdd=max(maxdd,peak-equity)

    pairs,cash=settle_pairs(pairs,cash,10**30,ledger)
    ld=pd.DataFrame(ledger)

    if ld.empty:
        raise RuntimeError("Aucune paire complète.")

    mk=ld.groupby("market_slug",as_index=False).agg(
        trades=("pnl","size"),pnl=("pnl","sum"),
        wins=("pnl",lambda s:int((s>0).sum()))
    ).sort_values("pnl",ascending=False)

    profit=cash-INITIAL_CAPITAL
    return {
        "leg1_budget":budget,
        "initial_capital":INITIAL_CAPITAL,
        "final_capital":float(cash),
        "profit":float(profit),
        "return_pct":float(profit/INITIAL_CAPITAL*100),
        "completed_pairs":int(len(ld)),
        "wins":int((ld.pnl>0).sum()),
        "losses":int((ld.pnl<=0).sum()),
        "win_rate_pct":float((ld.pnl>0).mean()*100),
        "max_drawdown":float(maxdd),
        "max_drawdown_pct":float(maxdd/peak*100 if peak else 0),
        "rejected_no_cash":rejected_no_cash,
        "hedge_reduced":reduced,
        "hedge_failed":failed,
        "leg1_exit_events":exit_leg1,
        "markets_traded":int(mk.market_slug.nunique()),
        "profitable_markets":int((mk.pnl>0).sum()),
        "losing_markets":int((mk.pnl<=0).sum()),
        "best_market_pnl":float(mk.pnl.max()),
        "worst_market_pnl":float(mk.pnl.min()),
    },ld,mk


def main():
    print("DB:",DB)
    raw=load_signals()
    print(f"RAW OBSERVATIONS: {len(raw):,}")
    print(f"MARKETS WITH SIGNAL: {raw.market_slug.nunique():,}")
    sig=dedup(raw)
    print(f"DEDUPLICATED SIGNALS: {len(sig):,}")
    print("RULE: 5m DOWN->UP | first_ask <= 0.14")
    print("CASH RELEASE: market expiry")
    print("FAILED/REDUCED HEDGE: unhedged LEG1 sold at recorded T0 bid; unfilled remainder valued at 0\n")

    OUT.mkdir(parents=True,exist_ok=True)
    sig.to_csv(OUT/"deduplicated_signals.csv",index=False)
    summaries=[]

    for b in LEG1_BUDGETS:
        s,ld,mk=simulate(sig,b)
        summaries.append(s)
        ld.to_csv(OUT/f"ledger_{int(b)}usdc.csv",index=False)
        mk.to_csv(OUT/f"markets_{int(b)}usdc.csv",index=False)

        print("="*72)
        print(f"LEG1 BUDGET = {b:.0f} USDC")
        print("="*72)
        print(f"Capital final   : {s['final_capital']:.2f}")
        print(f"Profit          : {s['profit']:+.2f} ({s['return_pct']:+.2f}%)")
        print(f"Paires complètes: {s['completed_pairs']}")
        print(f"Wins / Losses   : {s['wins']} / {s['losses']} ({s['win_rate_pct']:.2f}% wins)")
        print(f"Max drawdown    : {s['max_drawdown']:.2f} ({s['max_drawdown_pct']:.2f}%)")
        print(f"No cash         : {s['rejected_no_cash']}")
        print(f"Hedge réduit    : {s['hedge_reduced']}")
        print(f"Hedge impossible: {s['hedge_failed']}")
        print(f"Sorties LEG1    : {s['leg1_exit_events']}")
        print(f"Marchés + / -   : {s['profitable_markets']} / {s['losing_markets']}")
        print(f"Best/Worst marché: {s['best_market_pnl']:+.2f} / {s['worst_market_pnl']:+.2f}")
        print()

    pd.DataFrame(summaries).to_csv(OUT/"portfolio_v4_summary.csv",index=False)
    print("Résultats:",OUT)


if __name__=="__main__":
    main()
