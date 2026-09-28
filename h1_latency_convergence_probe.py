"""
H1 — Sonde de plausibilité : convergence tardive / latence Binance -> Polymarket
==================================================================================

LECTURE SEULE. Aucune écriture, aucun ordre, aucune connexion réseau.
A lancer localement sur la vraie base D5, ex. :

    python h1_latency_convergence_probe.py \
        --db "C:\\Users\\Ramy\\Documents\\polymarket-crypto\\data\\d5_24h_20260920_085530\\d5_live_24h_20260920_124822.db" \
        --out h1_probe_results

Ce script NE valide PAS H1. Il répond à une seule question : est-ce que le
signal grossier existe dans les données déjà collectées, assez pour justifier
une collecte plus longue et un vrai protocole TRAIN/VALIDATION/OOS ?

Méthode (volontairement simple, pas un modèle de pricing sophistiqué) :
  1. Pour chaque marché BTC 5m/15m, on prend le prix BTC au début du marché
     comme référence (ref_price).
  2. A chaque tick BTC suivant, on calcule le "signal directionnel" = signe de
     (btc_price - ref_price).
  3. A chaque snapshot du carnet Polymarket (book_sides, côté UP), on regarde
     si le prix affiché (mid ou ask) est cohérent avec ce signal directionnel
     ou s'il est "en retard" (encore proche de 0.5 alors que le signal BTC est
     déjà tranché depuis plusieurs secondes).
  4. Pour chaque épisode de retard détecté, on simule un achat au prix affiché
     (périmé) au moment de la détection, avec friction + délai d'exécution
     pessimiste ajouté, et on mesure le PnL si la position est tenue jusqu'à la
     prochaine mise à jour du carnet qui "rattrape" le signal (proxy de sortie,
     pas un vrai règlement à expiration -- limite explicite, voir rapport final).

Sorties : un CSV d'épisodes + un résumé imprimé en console avec edge net moyen,
nombre d'épisodes, et répartition par marché -- pour un premier coup d'oeil,
pas pour une décision finale.
"""

import argparse
import csv
import sqlite3
import statistics
from collections import defaultdict

# ---- Paramètres à calibrer en TRAIN uniquement (valeurs de départ, arbitraires) ----
BTC_MOVE_THRESHOLD_BPS = 5.0       # mouvement BTC minimum pour considérer un signal "tranché"
STALE_BAND = 0.10                  # le prix Polymarket est jugé "périmé" s'il reste dans [0.5-STALE_BAND, 0.5+STALE_BAND]
FRICTION_PER_SHARE = 0.005         # identique à D3/D4, pour comparabilité
PESSIMISTIC_EXEC_DELAY_MS = 250    # notre propre latence estimée, pessimiste
MIN_EPISODE_GAP_MS = 1000          # cooldown entre deux épisodes sur le même marché


def load_btc_ticks(con, session_id=None):
    """kind='BTC' events, payload_json contient un MarketTick sérialisé (dataclass asdict)."""
    import json
    q = "SELECT event_id, event_ts_ms, received_ts_ms, payload_json FROM events WHERE kind='BTC'"
    params = ()
    if session_id:
        q += " AND session_id=?"
        params = (session_id,)
    q += " ORDER BY event_id"
    rows = []
    for event_id, ets, rts, payload in con.execute(q, params):
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            continue
        price = data.get("price")
        if price is None:
            continue
        ts = ets if ets is not None else rts
        rows.append((ts, float(price)))
    return rows


def load_markets(con):
    q = "SELECT condition_id, market_slug, market_duration, expiry_ts_ms FROM markets"
    return {row[1]: {"condition_id": row[0], "duration": row[2], "expiry_ts_ms": row[3]}
            for row in con.execute(q)}


def load_book_up(con, market_slug):
    """Snapshots du carnet, côté UP uniquement, pour un marché donné."""
    q = """
    SELECT e.event_ts_ms, e.received_ts_ms, b.best_bid, b.best_ask
    FROM events e JOIN book_sides b ON b.event_id = e.event_id
    WHERE e.kind='BOOK' AND e.market_slug=? AND b.side='UP'
    ORDER BY e.event_id
    """
    rows = []
    for ets, rts, bid, ask in con.execute(q, (market_slug,)):
        ts = ets if ets is not None else rts
        if bid is None or ask is None:
            continue
        mid = (bid + ask) / 2.0
        rows.append((ts, bid, ask, mid))
    return rows


def market_start_ts(book_rows):
    return book_rows[0][0] if book_rows else None


def find_ref_btc_price(btc_ticks, start_ts):
    for ts, price in btc_ticks:
        if ts >= start_ts:
            return price, ts
    return None, None


def detect_episodes(market_slug, btc_ticks, book_rows):
    """Coeur de la sonde : détecte les épisodes 'signal BTC tranché mais prix Polymarket périmé'."""
    if not book_rows or not btc_ticks:
        return []

    start_ts = market_start_ts(book_rows)
    ref_price, ref_ts = find_ref_btc_price(btc_ticks, start_ts)
    if ref_price is None:
        return []

    episodes = []
    last_episode_ts = -1e18
    btc_idx = 0
    n_btc = len(btc_ticks)

    for ts, bid, ask, mid in book_rows:
        # avancer btc_idx jusqu'au dernier tick BTC <= ts
        while btc_idx + 1 < n_btc and btc_ticks[btc_idx + 1][0] <= ts:
            btc_idx += 1
        btc_ts, btc_price = btc_ticks[btc_idx]
        if btc_ts > ts:
            continue  # pas encore de tick BTC connu à ce moment

        move_bps = (btc_price - ref_price) / ref_price * 10000.0
        if abs(move_bps) < BTC_MOVE_THRESHOLD_BPS:
            continue  # signal BTC pas encore tranché

        signal_up = move_bps > 0
        poly_stale = (0.5 - STALE_BAND) <= mid <= (0.5 + STALE_BAND)
        if not poly_stale:
            continue  # le prix Polymarket a déjà bougé, pas un épisode de retard

        if ts - last_episode_ts < MIN_EPISODE_GAP_MS:
            continue  # cooldown

        entry_price = ask if signal_up else (1.0 - bid)  # prix pour acheter le côté favorisé
        episodes.append({
            "market_slug": market_slug,
            "detect_ts_ms": ts,
            "btc_move_bps": round(move_bps, 2),
            "signal_up": signal_up,
            "entry_price": entry_price,
            "ref_price": ref_price,
        })
        last_episode_ts = ts

    return episodes


def simulate_exit(book_rows, episode):
    """Sortie proxy : premier snapshot après le délai d'exécution pessimiste où le
    prix a nettement convergé (>0.8 ou <0.2) dans le sens du signal. Sinon, pas de
    sortie propre -> exclu (marqué incomplete), conformément à l'esprit du projet
    de ne pas inventer une récupération optimiste."""
    target_ts = episode["detect_ts_ms"] + PESSIMISTIC_EXEC_DELAY_MS
    for ts, bid, ask, mid in book_rows:
        if ts < target_ts:
            continue
        converged = (mid >= 0.85) if episode["signal_up"] else (mid <= 0.15)
        if converged:
            exit_price = bid if episode["signal_up"] else (1.0 - ask)
            return exit_price, ts
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Chemin vers d5_live_24h_*.db (lecture seule)")
    ap.add_argument("--out", default="h1_probe_results", help="Préfixe des fichiers de sortie")
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = None

    markets = load_markets(con)
    btc_ticks = load_btc_ticks(con)
    if not btc_ticks:
        print("Aucun tick BTC trouvé -- vérifier le chemin de la base.")
        return

    all_episodes = []
    for slug in markets:
        book_rows = load_book_up(con, slug)
        episodes = detect_episodes(slug, btc_ticks, book_rows)
        for ep in episodes:
            exit_price, exit_ts = simulate_exit(book_rows, ep)
            ep["exit_price"] = exit_price
            ep["exit_ts_ms"] = exit_ts
            ep["complete"] = exit_price is not None
            if ep["complete"]:
                gross = exit_price - ep["entry_price"]
                ep["net_edge"] = gross - FRICTION_PER_SHARE
            else:
                ep["net_edge"] = None
        all_episodes.extend(episodes)

    # --- Ecriture CSV ---
    out_csv = f"{args.out}.csv"
    fieldnames = ["market_slug", "detect_ts_ms", "btc_move_bps", "signal_up",
                  "entry_price", "exit_price", "exit_ts_ms", "complete", "net_edge"]
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ep in all_episodes:
            writer.writerow({k: ep.get(k) for k in fieldnames})

    # --- Résumé console ---
    complete = [e for e in all_episodes if e["complete"]]
    incomplete = len(all_episodes) - len(complete)
    print(f"Marchés analysés          : {len(markets)}")
    print(f"Episodes détectés         : {len(all_episodes)}")
    print(f"  dont sortie trouvée     : {len(complete)}")
    print(f"  dont incomplets (exclus): {incomplete}")
    if complete:
        edges = [e["net_edge"] for e in complete]
        print(f"Edge net moyen            : {statistics.mean(edges):.4f}")
        print(f"Edge net médian           : {statistics.median(edges):.4f}")
        print(f"Edge net positif          : {sum(1 for e in edges if e > 0)}/{len(edges)}")
        by_market = defaultdict(list)
        for e in complete:
            by_market[e["market_slug"]].append(e["net_edge"])
        n_markets_positive = sum(1 for v in by_market.values() if statistics.mean(v) > 0)
        print(f"Marchés à edge moyen>0    : {n_markets_positive}/{len(by_market)}")
    print(f"\nDétail écrit dans : {out_csv}")
    print("\nRAPPEL : ceci est un test de plausibilité sur 3h02 de données, pas une")
    print("validation. Ne pas interpréter un résultat positif comme un feu vert.")


if __name__ == "__main__":
    main()
