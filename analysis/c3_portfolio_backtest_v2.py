from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "c3_shadow_live.db"
OUT = ROOT / "analysis" / "c3_portfolio_v2_results"

INITIAL_CAPITAL = 500.0
LEG1_BUDGETS = (10.0, 20.0, 50.0)

# Règle D3 figée : aucune réoptimisation ici.
DURATION = "5m"
DIRECTION = "DOWN->UP"
MAX_FIRST_ASK = 0.14
COOLDOWN_MS = 15_000

# Hypothèse conservatrice déjà utilisée dans D3 :
# coût additionnel total de 0,005 USDC par paire (friction).
FRICTION_PER_PAIR = 0.005


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
                selected.append(row._asdict())
                last_ts = ts
    if not selected:
        return pd.DataFrame()
    return pd.DataFrame(selected).sort_values(
        ["anchor_ts_ms", "market_slug"]
    ).reset_index(drop=True)


def settle_due(open_positions, cash, now_ms, ledger):
    remaining = []
    for pos in open_positions:
        if pos["settle_ts"] <= now_ms:
            # Une paire complète paie 1 USDC par share.
            payout = pos["qty"] * 1.0
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
    peak_equity = INITIAL_CAPITAL
    max_drawdown = 0.0
    open_positions = []
    ledger = []
    skipped_cash_leg1 = 0
    hedge_reduced = 0
    hedge_failed = 0

    for row in signals.itertuples(index=False):
        now = int(row.anchor_ts_ms)

        # Pour ce backtest, on considère la paire réglée au moment où LEG2
        # est observée. Cela mesure le capital requis par les deux jambes
        # sans attendre l'expiration du marché.
        open_positions, cash = settle_due(
            open_positions, cash, now, ledger
        )

        p1 = float(row.first_ask)
        p2 = float(row.second_ask)
        q1_book = float(row.first_ask_qty)
        q2_book = float(row.second_ask_qty)

        # LEG1 : budget nominal en USDC, limité par le carnet et le cash.
        q1_target = leg1_budget / p1
        q1 = min(q1_target, q1_book, cash / p1)

        if q1 <= 0:
            skipped_cash_leg1 += 1
            continue

        leg1_cost = q1 * p1
        cash -= leg1_cost

        # LEG2 doit acheter LE MEME NOMBRE de shares pour former la paire.
        # Limitation réelle : profondeur LEG2 + cash restant.
        q2_cash = cash / (p2 + FRICTION_PER_PAIR)
        q_pair = min(q1, q2_book, q2_cash)

        if q_pair <= 0:
            # Impossible de couvrir : on annule comptablement ce candidat.
            # On ne prétend pas connaître la valeur finale de la jambe nue.
            cash += leg1_cost
            hedge_failed += 1
            continue

        if q_pair < q1:
            hedge_reduced += 1
            # La partie non couverte de LEG1 n'est pas simulée : on réduit
            # rétrospectivement la taille à la quantité effectivement pairable.
            refund = (q1 - q_pair) * p1
            cash += refund

        leg1_cost = q_pair * p1
        leg2_cost = q_pair * p2
        friction = q_pair * FRICTION_PER_PAIR
        total_cost = leg1_cost + leg2_cost + friction

        # LEG1 est déjà débité. Débiter LEG2 + friction.
        cash -= leg2_cost + friction

        if cash < -1e-8:
            raise RuntimeError("Invariant cash violé")

        # On utilise hedge_ts comme instant de libération de la paire.
        # Le payout = 1/share représente sa valeur certaine une fois pairée.
        open_positions.append({
            "anchor_ts_ms": int(row.anchor_ts_ms),
            "hedge_ts_ms": int(row.hedge_ts_ms),
            "settle_ts": int(row.hedge_ts_ms),
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
        })

        # Equity économique : cash + valeur certaine des paires complètes.
        equity = cash + sum(p["qty"] for p in open_positions)
        peak_equity = max(peak_equity, equity)
        max_drawdown = max(max_drawdown, peak_equity - equity)

    # Régler toutes les paires restantes.
    open_positions, cash = settle_due(
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
            wins=("pnl", lambda x: int((x > 0).sum())),
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
        "wins": int((ld.pnl > 0).sum()),
        "losses": int((ld.pnl <= 0).sum()),
        "win_rate_pct": float((ld.pnl > 0).mean() * 100),
        "max_drawdown": float(max_drawdown),
        "max_drawdown_pct": float(
            max_drawdown / peak_equity * 100 if peak_equity else 0
        ),
        "skipped_cash_leg1": skipped_cash_leg1,
        "hedge_reduced": hedge_reduced,
        "hedge_failed": hedge_failed,
        "profitable_markets": int((markets.pnl > 0).sum()),
        "losing_markets": int((markets.pnl <= 0).sum()),
        "best_market_pnl": float(markets.pnl.max()),
        "worst_market_pnl": float(markets.pnl.min()),
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
    print(f"FRICTION: {FRICTION_PER_PAIR:.3f} USDC/pair\n")

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
            f"Hedge réduit    : {result['hedge_reduced']} | "
            f"Hedge impossible: {result['hedge_failed']}"
        )
        print(
            f"Marchés + / -   : {result['profitable_markets']} / "
            f"{result['losing_markets']}"
        )
        print(
            f"Best/Worst marché: {result['best_market_pnl']:+.2f} / "
            f"{result['worst_market_pnl']:+.2f} USDC"
        )
        print()

    pd.DataFrame(summaries).to_csv(
        OUT / "portfolio_v2_summary.csv", index=False
    )

    print(f"Résultats enregistrés dans : {OUT}")


if __name__ == "__main__":
    main()
