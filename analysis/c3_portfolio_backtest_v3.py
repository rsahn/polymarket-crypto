from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "c3_shadow_live.db"
OUT = ROOT / "analysis" / "c3_portfolio_v3_results"

INITIAL_CAPITAL = 500.0
LEG1_BUDGETS = (10.0, 20.0, 50.0)

# Règle D3 figée.
DURATION = "5m"
DIRECTION = "DOWN->UP"
MAX_FIRST_ASK = 0.14
COOLDOWN_MS = 15_000

# Même hypothèse que D3/V2.
FRICTION_PER_PAIR = 0.005

# Les slugs BTC 5m se terminent par le timestamp UNIX du début du marché.
MARKET_LENGTH_MS = 5 * 60 * 1000


def market_end_ms(slug: str) -> int:
    m = re.search(r"-(\d+)$", str(slug))
    if not m:
        raise ValueError(f"Timestamp introuvable dans market_slug={slug!r}")
    return int(m.group(1)) * 1000 + MARKET_LENGTH_MS


def load_signals() -> pd.DataFrame:
    with sqlite3.connect(DB) as db:
        return pd.read_sql_query(
            """
            SELECT
                id, anchor_ts_ms, hedge_ts_ms, market_slug,
                market_duration, direction,
                first_ask, first_ask_qty,
                second_ask, second_ask_qty,
                executable_qty, pair_cost, gross_edge
            FROM c3_shadow_observations_v2
            WHERE market_slug IS NOT NULL
              AND market_slug NOT IN ('5m','15m')
              AND market_duration = ?
              AND direction = ?
              AND first_ask <= ?
            ORDER BY anchor_ts_ms, id
            """,
            db,
            params=(DURATION, DIRECTION, MAX_FIRST_ASK),
        )


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    selected = []
    for _, group in df.groupby("market_slug", sort=False):
        last_ts = None
        for row in group.sort_values("anchor_ts_ms").itertuples(index=False):
            ts = int(row.anchor_ts_ms)
            if last_ts is None or ts - last_ts >= COOLDOWN_MS:
                d = row._asdict()
                d["market_end_ms"] = market_end_ms(row.market_slug)
                selected.append(d)
                last_ts = ts
    return pd.DataFrame(selected).sort_values(
        ["anchor_ts_ms", "market_slug"]
    ).reset_index(drop=True)


def release_expired(open_positions, cash, now_ms, ledger):
    remaining = []
    for pos in open_positions:
        if pos["market_end_ms"] <= now_ms:
            payout = pos["qty"]  # 1 USDC par paire UP+DOWN
            cash += payout
            pos["payout"] = payout
            pos["pnl"] = payout - pos["total_cost"]
            pos["status"] = "SETTLED"
            ledger.append(pos)
        else:
            remaining.append(pos)
    return remaining, cash


def simulate(signals: pd.DataFrame, leg1_budget: float):
    cash = INITIAL_CAPITAL
    open_positions = []
    ledger = []

    skipped_no_cash = 0
    hedge_reduced = 0
    hedge_failed = 0

    peak_equity = INITIAL_CAPITAL
    max_drawdown = 0.0

    for row in signals.itertuples(index=False):
        now = int(row.anchor_ts_ms)
        open_positions, cash = release_expired(
            open_positions, cash, now, ledger
        )

        p1 = float(row.first_ask)
        p2 = float(row.second_ask)
        q1_book = float(row.first_ask_qty)
        q2_book = float(row.second_ask_qty)

        if cash <= 0:
            skipped_no_cash += 1
            continue

        # LEG1.
        q1_target = leg1_budget / p1
        q1 = min(q1_target, q1_book, cash / p1)
        if q1 <= 0:
            skipped_no_cash += 1
            continue

        leg1_cost_initial = q1 * p1
        cash -= leg1_cost_initial

        # LEG2 : même nombre de shares, limité par book et cash restant.
        q2_cash = cash / (p2 + FRICTION_PER_PAIR)
        q_pair = min(q1, q2_book, q2_cash)

        if q_pair <= 0:
            # On ne sait pas valoriser proprement une jambe nue avec cette DB.
            # Le candidat est donc rejeté et le coût LEG1 restitué dans le
            # backtest plutôt que d'inventer un PnL directionnel.
            cash += leg1_cost_initial
            hedge_failed += 1
            continue

        if q_pair < q1:
            hedge_reduced += 1
            cash += (q1 - q_pair) * p1

        leg1_cost = q_pair * p1
        leg2_cost = q_pair * p2
        friction = q_pair * FRICTION_PER_PAIR
        total_cost = leg1_cost + leg2_cost + friction

        cash -= leg2_cost + friction
        if cash < -1e-7:
            raise RuntimeError("Cash négatif : invariant violé.")

        open_positions.append(
            {
                "anchor_ts_ms": int(row.anchor_ts_ms),
                "hedge_ts_ms": int(row.hedge_ts_ms),
                "market_end_ms": int(row.market_end_ms),
                "market_slug": row.market_slug,
                "leg1_budget": leg1_budget,
                "first_ask": p1,
                "second_ask": p2,
                "qty": q_pair,
                "leg1_cost": leg1_cost,
                "leg2_cost": leg2_cost,
                "friction": friction,
                "total_cost": total_cost,
                "pair_cost_net": p1 + p2 + FRICTION_PER_PAIR,
                "status": "OPEN",
            }
        )

        # Une paire complète a une valeur certaine de qty à l'expiration,
        # mais ce montant n'est PAS réutilisable comme cash avant market_end.
        equity = cash + sum(p["qty"] for p in open_positions)
        peak_equity = max(peak_equity, equity)
        dd = peak_equity - equity
        max_drawdown = max(max_drawdown, dd)

    open_positions, cash = release_expired(
        open_positions, cash, 10**30, ledger
    )

    ld = pd.DataFrame(ledger)
    if ld.empty:
        raise RuntimeError("Aucune paire complète simulée.")

    markets = (
        ld.groupby("market_slug", as_index=False)
        .agg(
            trades=("pnl", "size"),
            pnl=("pnl", "sum"),
            wins=("pnl", lambda s: int((s > 0).sum())),
            total_cost=("total_cost", "sum"),
        )
        .sort_values("pnl", ascending=False)
    )

    profit = cash - INITIAL_CAPITAL
    result = {
        "leg1_budget": leg1_budget,
        "initial_capital": INITIAL_CAPITAL,
        "final_capital": float(cash),
        "profit": float(profit),
        "return_pct": float(profit / INITIAL_CAPITAL * 100),
        "completed_pairs": int(len(ld)),
        "wins": int((ld["pnl"] > 0).sum()),
        "losses": int((ld["pnl"] <= 0).sum()),
        "win_rate_pct": float((ld["pnl"] > 0).mean() * 100),
        "max_drawdown": float(max_drawdown),
        "max_drawdown_pct": float(
            max_drawdown / peak_equity * 100 if peak_equity else 0
        ),
        "skipped_no_cash": skipped_no_cash,
        "hedge_reduced": hedge_reduced,
        "hedge_failed": hedge_failed,
        "markets_traded": int(markets["market_slug"].nunique()),
        "profitable_markets": int((markets["pnl"] > 0).sum()),
        "losing_markets": int((markets["pnl"] <= 0).sum()),
        "best_market_pnl": float(markets["pnl"].max()),
        "worst_market_pnl": float(markets["pnl"].min()),
    }
    return result, ld, markets


def main():
    print(f"DB: {DB}")
    raw = load_signals()
    print(f"RAW OBSERVATIONS: {len(raw):,}")
    print(f"MARKETS WITH SIGNAL: {raw.market_slug.nunique():,}")

    signals = deduplicate(raw)
    print(f"DEDUPLICATED SIGNALS: {len(signals):,}")
    print(f"COOLDOWN: {COOLDOWN_MS / 1000:.0f}s")
    print("RULE: 5m DOWN->UP | first_ask <= 0.14")
    print(f"FRICTION: {FRICTION_PER_PAIR:.3f} USDC/pair")
    print("CASH RELEASE: only at real 5m market expiry\n")

    OUT.mkdir(parents=True, exist_ok=True)
    signals.to_csv(OUT / "deduplicated_signals.csv", index=False)

    summaries = []
    for budget in LEG1_BUDGETS:
        result, ledger, markets = simulate(signals, budget)
        summaries.append(result)

        ledger.to_csv(
            OUT / f"ledger_leg1_{int(budget)}usdc.csv", index=False
        )
        markets.to_csv(
            OUT / f"markets_leg1_{int(budget)}usdc.csv", index=False
        )

        print("=" * 72)
        print(f"LEG1 BUDGET = {budget:.0f} USDC")
        print("=" * 72)
        print(f"Capital initial : {result['initial_capital']:.2f}")
        print(f"Capital final   : {result['final_capital']:.2f}")
        print(
            f"Profit          : {result['profit']:+.2f} "
            f"({result['return_pct']:+.2f}%)"
        )
        print(f"Paires complètes: {result['completed_pairs']}")
        print(
            f"Wins / Losses   : {result['wins']} / {result['losses']} "
            f"({result['win_rate_pct']:.2f}% wins)"
        )
        print(
            f"Max drawdown    : {result['max_drawdown']:.2f} "
            f"({result['max_drawdown_pct']:.2f}%)"
        )
        print(
            f"Skipped cash    : {result['skipped_no_cash']} | "
            f"Hedge réduit: {result['hedge_reduced']} | "
            f"Hedge impossible: {result['hedge_failed']}"
        )
        print(
            f"Marchés tradés  : {result['markets_traded']} | "
            f"+ / - : {result['profitable_markets']} / "
            f"{result['losing_markets']}"
        )
        print(
            f"Best/Worst marché: {result['best_market_pnl']:+.2f} / "
            f"{result['worst_market_pnl']:+.2f} USDC"
        )
        print()

    pd.DataFrame(summaries).to_csv(
        OUT / "portfolio_v3_summary.csv", index=False
    )
    print(f"Résultats enregistrés dans : {OUT}")


if __name__ == "__main__":
    main()
