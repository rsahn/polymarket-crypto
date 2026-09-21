from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "c3_shadow_live.db"
OUT = ROOT / "analysis" / "c3_v21_results"

TRAIN_RATIO = 0.60
VALIDATION_RATIO = 0.20

MIN_TRAIN_MARKETS = 20
MIN_VALIDATION_MARKETS = 5
MIN_OOS_MARKETS = 5

# Variables connues à T0 uniquement.
FEATURES = [
    "first_ask",
    "first_spread",
    "first_ask_qty",
    "first_bid_qty",
    "opposite_ask",
    "opposite_spread",
    "opposite_ask_qty",
    "opposite_bid_qty",
    "depth_imbalance",
    "btc_return_1s",
    "btc_return_5s",
    "btc_return_15s",
    "time_remaining_ms",
]


def load_data() -> pd.DataFrame:
    print(f"DB: {DB}")

    with sqlite3.connect(DB) as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                anchor_ts_ms,
                hedge_ts_ms,
                delay_ms,
                market_key,
                market_slug,
                condition_id,
                market_duration,
                anchor_group,
                direction,

                btc_price,
                btc_return_1s,
                btc_return_5s,
                btc_return_15s,
                time_remaining_ms,

                first_bid,
                first_ask,
                first_bid_qty,
                first_ask_qty,
                first_spread,

                opposite_bid,
                opposite_ask,
                opposite_bid_qty,
                opposite_ask_qty,
                opposite_spread,
                depth_imbalance,

                second_ask,
                second_ask_qty,
                executable_qty,

                pair_cost,
                gross_edge,
                net_edge_005

            FROM c3_shadow_observations_v2

            WHERE market_slug IS NOT NULL
              AND market_slug NOT IN ('5m', '15m')
            ORDER BY anchor_ts_ms
            """,
            conn,
        )

    if df.empty:
        raise RuntimeError("Aucune observation V2.1 trouvée.")

    print(f"ROWS: {len(df):,}")
    print(f"REAL MARKETS: {df.market_slug.nunique():,}")

    return df


def split_by_market(df: pd.DataFrame):
    markets = (
        df.groupby("market_slug", as_index=False)
        .agg(
            first_ts=("anchor_ts_ms", "min"),
            duration=("market_duration", "first"),
        )
        .sort_values("first_ts")
        .reset_index(drop=True)
    )

    n = len(markets)

    train_end = int(n * TRAIN_RATIO)
    validation_end = int(n * (TRAIN_RATIO + VALIDATION_RATIO))

    train_markets = set(markets.iloc[:train_end].market_slug)
    validation_markets = set(
        markets.iloc[train_end:validation_end].market_slug
    )
    oos_markets = set(markets.iloc[validation_end:].market_slug)

    train = df[df.market_slug.isin(train_markets)].copy()
    validation = df[df.market_slug.isin(validation_markets)].copy()
    oos = df[df.market_slug.isin(oos_markets)].copy()

    print("\n=== CHRONOLOGICAL MARKET SPLIT ===")
    print(
        f"TRAIN      markets={len(train_markets)} "
        f"rows={len(train):,}"
    )
    print(
        f"VALIDATION markets={len(validation_markets)} "
        f"rows={len(validation):,}"
    )
    print(
        f"OOS TEST   markets={len(oos_markets)} "
        f"rows={len(oos):,}"
    )

    assert train_markets.isdisjoint(validation_markets)
    assert train_markets.isdisjoint(oos_markets)
    assert validation_markets.isdisjoint(oos_markets)

    return train, validation, oos, markets


def metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "rows": 0,
            "markets": 0,
            "positive_pct": None,
            "mean_net_edge": None,
            "median_net_edge": None,
            "weighted_net_edge": None,
            "total_executable_qty": 0.0,
        }

    edge = df["net_edge_005"].astype(float)
    qty = df["executable_qty"].fillna(0).astype(float)

    qty_sum = qty.sum()

    weighted = (
        float(np.average(edge, weights=qty))
        if qty_sum > 0
        else None
    )

    return {
        "rows": int(len(df)),
        "markets": int(df.market_slug.nunique()),
        "positive_pct": float((edge > 0).mean() * 100),
        "mean_net_edge": float(edge.mean()),
        "median_net_edge": float(edge.median()),
        "weighted_net_edge": weighted,
        "total_executable_qty": float(qty_sum),
    }


def baseline_report(train, validation, oos):
    print("\n=== BASELINES ===")

    result = {}

    for duration in ("5m", "15m"):
        for direction in ("UP->DOWN", "DOWN->UP"):

            name = f"{duration}_{direction}"

            result[name] = {}

            print(f"\n{name}")

            for split_name, frame in (
                ("train", train),
                ("validation", validation),
                ("oos", oos),
            ):
                subset = frame[
                    (frame.market_duration == duration)
                    & (frame.direction == direction)
                ]

                m = metrics(subset)
                result[name][split_name] = m

                print(
                    f"  {split_name:10s} "
                    f"markets={m['markets']:3d} "
                    f"rows={m['rows']:7d} "
                    f"pos={m['positive_pct']} "
                    f"mean={m['mean_net_edge']} "
                    f"median={m['median_net_edge']} "
                    f"weighted={m['weighted_net_edge']}"
                )

    return result


def quantile_thresholds(train: pd.DataFrame):
    thresholds = {}

    for feature in FEATURES:
        values = train[feature].dropna()

        if len(values) < 100:
            continue

        q = values.quantile(
            [0.10, 0.20, 0.30, 0.40, 0.50,
             0.60, 0.70, 0.80, 0.90]
        )

        thresholds[feature] = sorted(set(float(x) for x in q.values))

    return thresholds


def apply_rule(
    df: pd.DataFrame,
    duration: str,
    direction: str,
    feature: str,
    operator: str,
    threshold: float,
):
    mask = (
        (df.market_duration == duration)
        & (df.direction == direction)
        & df[feature].notna()
    )

    if operator == "<=":
        mask &= df[feature] <= threshold
    else:
        mask &= df[feature] >= threshold

    return df[mask]


def discover_single_feature_candidates(train: pd.DataFrame):
    """
    Candidate discovery uses TRAIN ONLY.

    Validation and OOS are deliberately untouched here.
    """

    thresholds = quantile_thresholds(train)

    candidates = []

    for duration in ("5m", "15m"):
        for direction in ("UP->DOWN", "DOWN->UP"):

            for feature, feature_thresholds in thresholds.items():

                for threshold in feature_thresholds:
                    for operator in ("<=", ">="):

                        subset = apply_rule(
                            train,
                            duration,
                            direction,
                            feature,
                            operator,
                            threshold,
                        )

                        m = metrics(subset)

                        if m["markets"] < MIN_TRAIN_MARKETS:
                            continue

                        if m["rows"] < 100:
                            continue

                        candidates.append(
                            {
                                "duration": duration,
                                "direction": direction,
                                "feature": feature,
                                "operator": operator,
                                "threshold": threshold,
                                **m,
                            }
                        )

    # Ranking TRAIN uniquement.
    candidates.sort(
        key=lambda x: (
            x["weighted_net_edge"]
            if x["weighted_net_edge"] is not None
            else -999,
            x["markets"],
        ),
        reverse=True,
    )

    return candidates


def validate_candidates(
    candidates,
    validation: pd.DataFrame,
):
    """
    VALIDATION is used only after candidate discovery.
    OOS remains completely untouched.
    """

    validated = []

    for candidate in candidates:

        subset = apply_rule(
            validation,
            candidate["duration"],
            candidate["direction"],
            candidate["feature"],
            candidate["operator"],
            candidate["threshold"],
        )

        vm = metrics(subset)

        if vm["markets"] < MIN_VALIDATION_MARKETS:
            continue

        validated.append(
            {
                **candidate,
                "validation": vm,
            }
        )

    # Rank using validation performance, not OOS.
    validated.sort(
        key=lambda x: (
            x["validation"]["weighted_net_edge"]
            if x["validation"]["weighted_net_edge"] is not None
            else -999,
            x["validation"]["markets"],
        ),
        reverse=True,
    )

    return validated


def evaluate_oos_once(
    validated,
    oos: pd.DataFrame,
    top_n: int = 10,
):
    """
    OOS is opened only here, after discovery + validation.
    """

    results = []

    for candidate in validated[:top_n]:

        subset = apply_rule(
            oos,
            candidate["duration"],
            candidate["direction"],
            candidate["feature"],
            candidate["operator"],
            candidate["threshold"],
        )

        om = metrics(subset)

        results.append(
            {
                **candidate,
                "oos": om,
            }
        )

    return results


def print_final(results):
    print("\n")
    print("=" * 80)
    print("FINAL OOS RESULTS")
    print("=" * 80)

    for i, result in enumerate(results, 1):

        print(
            f"\n#{i} "
            f"{result['duration']} "
            f"{result['direction']} | "
            f"{result['feature']} "
            f"{result['operator']} "
            f"{result['threshold']:.8f}"
        )

        print(
            " TRAIN      "
            f"markets={result['markets']} "
            f"rows={result['rows']} "
            f"pos={result['positive_pct']:.2f}% "
            f"mean={result['mean_net_edge']:.6f} "
            f"median={result['median_net_edge']:.6f} "
            f"weighted={result['weighted_net_edge']:.6f}"
        )

        v = result["validation"]

        print(
            " VALIDATION "
            f"markets={v['markets']} "
            f"rows={v['rows']} "
            f"pos={v['positive_pct']:.2f}% "
            f"mean={v['mean_net_edge']:.6f} "
            f"median={v['median_net_edge']:.6f} "
            f"weighted={v['weighted_net_edge']:.6f}"
        )

        o = result["oos"]

        print(
            " OOS        "
            f"markets={o['markets']} "
            f"rows={o['rows']} "
            f"pos={o['positive_pct']:.2f}% "
            f"mean={o['mean_net_edge']:.6f} "
            f"median={o['median_net_edge']:.6f} "
            f"weighted={o['weighted_net_edge']:.6f}"
        )


def save_results(
    markets,
    baselines,
    candidates,
    validated,
    oos_results,
):
    OUT.mkdir(parents=True, exist_ok=True)

    markets.to_csv(
        OUT / "market_split.csv",
        index=False,
    )

    with open(
        OUT / "baseline.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(baselines, f, indent=2)

    with open(
        OUT / "train_candidates.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(candidates[:100], f, indent=2)

    with open(
        OUT / "validated_candidates.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(validated[:50], f, indent=2)

    with open(
        OUT / "oos_results.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(oos_results, f, indent=2)

    print(f"\nResults saved to: {OUT}")


def main():
    df = load_data()

    train, validation, oos, markets = split_by_market(df)

    baselines = baseline_report(
        train,
        validation,
        oos,
    )

    print("\n=== TRAIN CANDIDATE DISCOVERY ===")

    candidates = discover_single_feature_candidates(train)

    print(f"TRAIN candidates: {len(candidates)}")

    print("\n=== VALIDATION ===")

    validated = validate_candidates(
        candidates,
        validation,
    )

    print(f"Validated candidates: {len(validated)}")

    # OOS is accessed only after the preceding steps.
    oos_results = evaluate_oos_once(
        validated,
        oos,
        top_n=10,
    )

    print_final(oos_results)

    save_results(
        markets,
        baselines,
        candidates,
        validated,
        oos_results,
    )


if __name__ == "__main__":
    main()