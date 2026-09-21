import asyncio
import os
import time
from pathlib import Path

from app.collectors.binance import BinanceCollector
from app.collectors.polymarket import PolymarketMarketDiscovery
from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from app.paper.live import ChampionV1, PaperAudit
from app.paper.c3_observer import C3ShadowObserver
from app.storage.db import Database


ROOT = Path(__file__).resolve().parents[2]

DB_PATH = os.getenv(
    "DATABASE_PATH",
    str(ROOT / "data" / "poly_quant.db"),
)

PAPER_DB_PATH = os.getenv(
    "PAPER_DATABASE_PATH",
    str(ROOT / "data" / "paper_live.db"),
)

# Do not restart a market collector when rotation is imminent.
RESTART_SKIP_NEAR_EXPIRY_MS = int(
    os.getenv("RESTART_SKIP_NEAR_EXPIRY_MS", "20000")
)

CHAMPION_PATH = Path(
    os.getenv(
        "CHAMPION_PATH",
        str(ROOT / "analysis" / "bonereaper" / "d2" / "champion_v1.json"),
    )
)


async def legacy_main():
    raise RuntimeError('Historical C3 collection is retired. Run backend/run_d5.py (SHADOW only).')
    # ==============================================================
    # INITIALISATION
    # ==============================================================

    db = Database(DB_PATH)
    await db.init()

    champion = ChampionV1.load(CHAMPION_PATH)

    paper = PaperAudit(
        Path(PAPER_DB_PATH),
        float(os.getenv("MAX_PAPER_CAPITAL", "500.0")),
        os.getenv("PAPER_SHADOW", "true").lower() == "true",
        champion,
        fee_rate=float(os.getenv("PAPER_FEE_RATE", "0.0")),
        slippage=float(os.getenv("PAPER_SLIPPAGE", "0.0")),
        max_unhedged=float(os.getenv("PAPER_MAX_UNHEDGED", "2.0")),
    )

    c3_observer = C3ShadowObserver(
        ROOT / "data" / "c3_shadow_live.db",
        min_delay_ms=15_000,
        max_delay_ms=30_000,
        anchor_interval_ms=1_000,
    )
    await paper.init(int(time.time() * 1000))

    print(
        f'PAPER LIVE: mode={"SHADOW" if paper.shadow else "ACTIVE"} | '
        f'equity={paper.initial_equity:.2f} USDC | '
        f'champion={champion.name}'
    )

    if not champion.validated:
        print(f"CHAMPION_NOT_VALIDATED: {champion.reason}")

    # ==============================================================
    # RUNTIME STATE
    # ==============================================================

    stats = {
        "btc": 0,
        "poly": 0,
        "latest_btc": None,
        "latest": {},
        "states": {
            "5m": "WAITING_BOOK",
            "15m": "WAITING_BOOK",
        },
        "metrics": {},
        "rotations": {
            "5m": 0,
            "15m": 0,
        },
        "last_valid_book_monotonic": {},
    }

    # ==============================================================
    # BINANCE
    # ==============================================================

    async def on_tick(tick):
        await db.insert_btc(tick)
        stats["btc"] += 1
        stats["latest_btc"] = tick

    # ==============================================================
    # VALID POLYMARKET SNAPSHOT
    # ==============================================================

    async def on_quote(snapshot):
        remaining = snapshot.get("time_remaining_ms")

        if remaining is not None and remaining <= 0:
            return

        up = snapshot.get("up") or {}
        down = snapshot.get("down") or {}

        if any(up.get(field) is None for field in ("bid", "ask")):
            return

        if any(down.get(field) is None for field in ("bid", "ask")):
            return

        # Safety: never persist crossed/invalid books.
        if up["bid"] >= up["ask"] or down["bid"] >= down["ask"]:
            return

        await db.insert_poly_snapshot(snapshot)

        market_key = snapshot["market_key"]

        stats["poly"] += 1
        stats["latest"][market_key] = snapshot

        now_ms = int(time.time() * 1000)

        stats["last_valid_book_monotonic"][market_key] = time.monotonic()

        stats["metrics"][market_key] = {
            "feed_age_ms": 0,
            "processing_latency_ms": max(
                0,
                now_ms - snapshot["recv_ts_ms"],
            ),
            "decision_latency_ms": 0,
            "websocket_rtt_ms": None,
        }

        btc_price = None

        if stats["latest_btc"] is not None:
            btc_price = stats["latest_btc"].price

        await paper.record_snapshot(
            snapshot,
            btc_price,
            now_ms,
        )

        # C3 Shadow Observer: observation only, zero virtual or real orders.
        c3_observer.observe(snapshot, btc_price, now_ms)

        # Paper C3 Temporal V2 housekeeping only.
        # No automatic LEG 1 is opened until an evidence-backed entry rule is bound.
        expired_trade_ids = await paper.expire_temporal_trades(now_ms)
        for trade_id in expired_trade_ids:
            print(f"PAPER C3 FAILED_HEDGE: trade_id={trade_id}")

    # ==============================================================
    # CONSOLE OUTPUT
    # ==============================================================

    async def control_output():
        while True:
            await asyncio.sleep(1)

            btc = stats["latest_btc"]

            if btc is None:
                continue

            lines = [
                (
                    f"BTC LIVE: {btc.price:.2f} | "
                    f"Binance WS: CONNECTED | "
                    f"Polymarket WS: CONNECTED"
                )
            ]

            for key in ("5m", "15m"):
                state = stats["states"].get(key, "WAITING_BOOK")

                lines.append(
                    f"BTC {key.upper()} STATE: {state}"
                )

                snapshot = stats["latest"].get(key)

                if snapshot is None:
                    lines.append(
                        f"BTC {key.upper()}: waiting for live order book"
                    )
                    continue

                up = snapshot.get("up") or {}
                down = snapshot.get("down") or {}

                remaining = snapshot.get("time_remaining_ms")

                if remaining is None:
                    remaining_text = "n/a"
                else:
                    remaining_text = f"{remaining / 1000:.0f}s"

                if up.get("bid") is not None and up.get("ask") is not None:
                    spread_up = up["ask"] - up["bid"]
                else:
                    spread_up = "n/a"

                if down.get("bid") is not None and down.get("ask") is not None:
                    spread_down = down["ask"] - down["bid"]
                else:
                    spread_down = "n/a"

                lines.append(
                    f"BTC {key.upper()}: "
                    f"UP {up.get('bid')} / {up.get('ask')} "
                    f"(qty {up.get('bid_qty')}/{up.get('ask_qty')}) | "
                    f"DOWN {down.get('bid')} / {down.get('ask')} "
                    f"(qty {down.get('bid_qty')}/{down.get('ask_qty')}) | "
                    f"spread UP {spread_up} | "
                    f"spread DOWN {spread_down} | "
                    f"remaining {remaining_text}"
                )

                metrics = stats["metrics"].get(key, {})

                last_valid = stats[
                    "last_valid_book_monotonic"
                ].get(key)

                if last_valid is not None:
                    metrics["feed_age_ms"] = int(
                        (time.monotonic() - last_valid) * 1000
                    )

                lines.append(
                    f"{key.upper()} metrics: "
                    f"websocket_rtt_ms="
                    f"{metrics.get('websocket_rtt_ms', 'n/a')} "
                    f"feed_age_ms="
                    f"{metrics.get('feed_age_ms', 'n/a')} "
                    f"processing_latency_ms="
                    f"{metrics.get('processing_latency_ms', 'n/a')} "
                    f"decision_latency_ms="
                    f"{metrics.get('decision_latency_ms', 'n/a')}"
                )

            lines.append(
                f"SQLite: OK | "
                f"BTC ticks: {stats['btc']} | "
                f"snapshots: {stats['poly']}"
            )

            print("\n".join(lines))

    # ==============================================================
    # SAFE TASK CANCELLATION
    # ==============================================================

    async def cancel_task_safely(task, label, timeout=0.75):
        """Best-effort cancellation that never blocks recovery.

        A websocket coroutine may swallow/delay CancelledError while its socket is
        stuck.  Recovery must not wait for that old task.  The generation fence
        in run_market_session makes any late callback from such a zombie task a
        no-op.
        """
        if task is None:
            return True

        if task.done():
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                print(f"TASK_RESULT_ERROR ({label}): {exc}")
            return True

        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=timeout)

        if task not in done:
            print(f"TASK_CANCEL_DETACHED ({label})")
            return False

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"TASK_CANCEL_ERROR ({label}): {exc}")
        return True

    # ==============================================================
    # MARKET SESSION
    # ==============================================================

    async def run_market_session(market_key, market):
        """
        Run one market until expiry.

        If the order book becomes stale or the collector stops,
        recreate a fresh collector for the same market.

        Return to rotate_market when the market expires.
        """

        state_holder = {
            "state": "WAITING_BOOK",
        }

        stats["states"][market_key] = "WAITING_BOOK"

        # Every collector instance gets a generation number. If an old websocket
        # task refuses to die promptly, its late callbacks are ignored forever.
        collector_generation = 0
        consecutive_start_failures = 0

        while True:
            # ------------------------------------------------------
            # EXPIRY CHECK BEFORE STARTING A NEW COLLECTOR
            # ------------------------------------------------------

            now_ms = int(time.time() * 1000)
            expiry_ts_ms = market.get("expiry_ts_ms")

            if expiry_ts_ms is not None:
                remaining_ms = expiry_ts_ms - now_ms

                if remaining_ms <= 0:
                    state_holder["state"] = "EXPIRED"
                    stats["states"][market_key] = "EXPIRED"

                    print(
                        f"SESSION_EXPIRED ({market_key}): "
                        f"slug={market.get('slug')}"
                    )
                    return

                # No point starting another WS collector when
                # market rotation is imminent.
                if remaining_ms <= RESTART_SKIP_NEAR_EXPIRY_MS:
                    state_holder["state"] = "EXPIRED"
                    stats["states"][market_key] = "EXPIRED"

                    print(
                        f"COLLECTOR_START_SKIPPED_NEAR_EXPIRY ({market_key}): "
                        f"remaining_ms={remaining_ms}"
                    )
                    return

            # ------------------------------------------------------
            # FRESH SESSION STATE
            # ------------------------------------------------------

            collector_generation += 1
            my_generation = collector_generation
            first_valid_book = asyncio.Event()
            invalid_book_restart = asyncio.Event()
            invalid_book_count = 0

            state_holder["state"] = "WAITING_BOOK"
            stats["states"][market_key] = "WAITING_BOOK"

            # Never reuse a previous collector's book.
            stats["latest"].pop(market_key, None)
            stats["metrics"].pop(market_key, None)
            stats["last_valid_book_monotonic"].pop(
                market_key,
                None,
            )

            # ------------------------------------------------------
            # CALLBACK FOR THIS COLLECTOR INSTANCE
            # ------------------------------------------------------

            async def on_rotated_quote(snapshot):
                nonlocal invalid_book_count, consecutive_start_failures

                # Hard generation fence: a detached/zombie collector can never
                # reactivate the market or overwrite a newer book.
                if my_generation != collector_generation:
                    return

                # Token fence: never accept a callback for another market.
                snapshot_tokens = snapshot.get("token_ids")
                if snapshot_tokens is not None and snapshot_tokens != market.get("token_ids"):
                    print(f"STALE_COLLECTOR_CALLBACK_BLOCKED ({market_key})")
                    return

                remaining = snapshot.get("time_remaining_ms")

                if remaining is not None and remaining <= 0:
                    state_holder["state"] = "EXPIRED"
                    stats["states"][market_key] = "EXPIRED"

                    print(
                        f"STALE_MARKET_TRADING_BLOCKED ({market_key})"
                    )
                    return

                up = snapshot.get("up") or {}
                down = snapshot.get("down") or {}

                # Missing side/book.
                if any(
                    up.get(field) is None
                    for field in ("bid", "ask")
                ) or any(
                    down.get(field) is None
                    for field in ("bid", "ask")
                ):
                    state_holder["state"] = "WAITING_BOOK"
                    stats["states"][market_key] = "WAITING_BOOK"
                    return

                # Crossed or otherwise invalid book.
                if (
                    up["bid"] >= up["ask"]
                    or down["bid"] >= down["ask"]
                ):
                    invalid_book_count += 1
                    state_holder["state"] = "WAITING_BOOK"
                    stats["states"][market_key] = "WAITING_BOOK"

                    # A single transient crossed snapshot is blocked. If the
                    # collector keeps emitting crossed books, force a brand-new
                    # collector instance so its internal order-book state is reset.
                    if invalid_book_count == 1 or invalid_book_count >= 3:
                        print(
                            f"INVALID_BOOK_BLOCKED ({market_key}): "
                            f'UP={up["bid"]}/{up["ask"]} '
                            f'DOWN={down["bid"]}/{down["ask"]} '
                            f'count={invalid_book_count}'
                        )
                    if invalid_book_count >= 3:
                        invalid_book_restart.set()
                    return

                # A coherent full snapshot clears all recovery streaks.
                invalid_book_count = 0
                consecutive_start_failures = 0

                # First valid book / recovery.
                if state_holder["state"] != "ACTIVE":
                    state_holder["state"] = "ACTIVE"
                    stats["states"][market_key] = "ACTIVE"

                    if not first_valid_book.is_set():
                        first_valid_book.set()

                    print(
                        f"ACTIVE {market_key}: "
                        f'slug={market["slug"]} '
                        f'tokens={market["token_ids"]}'
                    )

                # Attach immutable market identity to every accepted snapshot.
                metadata = market.get("metadata") or {}
                snapshot["market_slug"] = market["slug"]
                snapshot["condition_id"] = metadata.get(
                    "conditionId",
                    market["slug"],
                )

                await on_quote(snapshot)

            # ------------------------------------------------------
            # START FRESH COLLECTOR
            # ------------------------------------------------------

            collector = PolymarketOrderbookCollector(
                market_key,
                market["token_ids"],
                on_rotated_quote,
                market.get("expiry_ts_ms"),
            )

            collector_task = asyncio.create_task(
                collector.run(),
                name=f"{market_key}-collector",
            )

            # Explicit task so Event.wait() can always be cancelled.
            first_book_task = asyncio.create_task(
                first_valid_book.wait(),
                name=f"{market_key}-first-valid-book",
            )
            invalid_book_task = asyncio.create_task(
                invalid_book_restart.wait(),
                name=f"{market_key}-invalid-book-restart",
            )

            valid_book_received = False
            restart_collector = False

            # ------------------------------------------------------
            # INITIAL 5 SECOND BOOK WATCHDOG
            # ------------------------------------------------------

            try:
                done, _ = await asyncio.wait(
                    {
                        collector_task,
                        first_book_task,
                        invalid_book_task,
                    },
                    timeout=5,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if first_book_task in done:
                    try:
                        first_book_task.result()
                    except asyncio.CancelledError:
                        pass

                    valid_book_received = True

                elif invalid_book_task in done:
                    print(f"INVALID_BOOK_RESTART ({market_key})")
                    restart_collector = True

                elif collector_task in done:
                    try:
                        collector_task.result()

                    except asyncio.CancelledError:
                        pass

                    except Exception as exc:
                        print(
                            f"COLLECTOR_TASK_ERROR "
                            f"({market_key}): {exc}"
                        )

                    print(
                        f"COLLECTOR_ENDED_BEFORE_BOOK "
                        f"({market_key})"
                    )

                    restart_collector = True

                else:
                    print(
                        f"WAITING_BOOK_TIMEOUT ({market_key})"
                    )

                    restart_collector = True

            finally:
                # This is the important Event.wait() cleanup.
                if not first_book_task.done():
                    await cancel_task_safely(
                        first_book_task,
                        f"{market_key}-first-valid-book",
                    )
                if not invalid_book_task.done():
                    await cancel_task_safely(
                        invalid_book_task,
                        f"{market_key}-invalid-book-restart",
                    )

            # ------------------------------------------------------
            # INITIAL BOOK FAILED
            # ------------------------------------------------------

            if restart_collector:
                # Invalidate this generation BEFORE cancellation. Even if the old
                # task is stuck, it is immediately unable to publish callbacks.
                collector_generation += 1
                consecutive_start_failures += 1
                await cancel_task_safely(
                    collector_task,
                    f"{market_key}-collector",
                )

                now_ms = int(time.time() * 1000)
                expiry_ts_ms = market.get("expiry_ts_ms")

                if expiry_ts_ms is not None:
                    remaining_ms = expiry_ts_ms - now_ms

                    if remaining_ms <= RESTART_SKIP_NEAR_EXPIRY_MS:
                        state_holder["state"] = "EXPIRED"
                        stats["states"][market_key] = "EXPIRED"

                        print(
                            f"COLLECTOR_RESTART_SKIPPED_NEAR_EXPIRY "
                            f"({market_key}): "
                            f"remaining_ms={remaining_ms}"
                        )
                        return

                # Avoid reconnect storms while still retrying fast enough for 5m.
                await asyncio.sleep(min(0.5 * consecutive_start_failures, 2.0))
                continue

            if not valid_book_received:
                await cancel_task_safely(
                    collector_task,
                    f"{market_key}-collector",
                )
                continue

            # ------------------------------------------------------
            # ACTIVE MONITORING
            # ------------------------------------------------------

            active_invalid_book_task = asyncio.create_task(
                invalid_book_restart.wait(),
                name=f"{market_key}-active-invalid-book-restart",
            )

            while True:
                done, _ = await asyncio.wait(
                    {collector_task, active_invalid_book_task},
                    timeout=2,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # --------------------------------------------------
                # INVALID/CROSSED BOOK BURST: hard resync
                # --------------------------------------------------

                if active_invalid_book_task in done:
                    print(f"INVALID_BOOK_HARD_RESYNC ({market_key})")
                    collector_generation += 1
                    await cancel_task_safely(
                        collector_task,
                        f"{market_key}-collector",
                    )
                    break

                # --------------------------------------------------
                # COLLECTOR STOPPED
                # --------------------------------------------------

                if collector_task in done:
                    try:
                        collector_task.result()

                    except asyncio.CancelledError:
                        pass

                    except Exception as exc:
                        print(
                            f"COLLECTOR_TASK_ERROR "
                            f"({market_key}): {exc}"
                        )

                    now_ms = int(time.time() * 1000)
                    expiry_ts_ms = market.get("expiry_ts_ms")

                    if expiry_ts_ms is not None:
                        remaining_ms = expiry_ts_ms - now_ms

                        if remaining_ms <= RESTART_SKIP_NEAR_EXPIRY_MS:
                            state_holder["state"] = "EXPIRED"
                            stats["states"][market_key] = "EXPIRED"

                            print(
                                f"COLLECTOR_RESTART_SKIPPED_NEAR_EXPIRY "
                                f"({market_key})"
                            )
                            return

                    print(
                        f"COLLECTOR_RESTART ({market_key})"
                    )

                    break

                # --------------------------------------------------
                # INDEPENDENT EXPIRY WATCHDOG
                # --------------------------------------------------

                now_ms = int(time.time() * 1000)
                expiry_ts_ms = market.get("expiry_ts_ms")

                if (
                    expiry_ts_ms is not None
                    and expiry_ts_ms <= now_ms
                ):
                    state_holder["state"] = "EXPIRED"
                    stats["states"][market_key] = "EXPIRED"

                    print(
                        f"SESSION_EXPIRED_WATCHDOG "
                        f"({market_key})"
                    )

                    collector_generation += 1
                    await cancel_task_safely(
                        collector_task,
                        f"{market_key}-collector",
                    )

                    return

                # --------------------------------------------------
                # STALE BOOK WATCHDOG
                # --------------------------------------------------

                last_valid = stats[
                    "last_valid_book_monotonic"
                ].get(market_key)

                if last_valid is None:
                    stale_for = None
                else:
                    stale_for = (
                        time.monotonic()
                        - last_valid
                    )

                if (
                    stale_for is not None
                    and stale_for > 10
                ):
                    state_holder["state"] = "WAITING_BOOK"
                    stats["states"][market_key] = "WAITING_BOOK"

                    print(
                        f"STALE_BOOK_RECOVERY "
                        f"{market_key}: "
                        f"stale_for={stale_for:.1f}s"
                    )

                    collector_generation += 1
                    await cancel_task_safely(
                        collector_task,
                        f"{market_key}-collector",
                    )

                    break

            if not active_invalid_book_task.done():
                await cancel_task_safely(
                    active_invalid_book_task,
                    f"{market_key}-active-invalid-book-restart",
                )

            # Outer while recreates the collector for SAME market.
            continue

    # ==============================================================
    # MARKET ROTATION
    # ==============================================================

    async def rotate_market(market_key):
        previous_slug = None

        while True:
            print(f"ROTATING {market_key}")

            try:
                markets = (
                    PolymarketMarketDiscovery
                    .get_active_btc_markets()
                )

            except Exception as exc:
                print(
                    f"MARKET_DISCOVERY_ERROR "
                    f"({market_key}): {exc}"
                )

                await asyncio.sleep(5)
                continue

            now_ms = int(time.time() * 1000)

            market = next(
                (
                    item
                    for item in markets
                    if (
                        item.get("market_key")
                        == market_key
                        and item.get(
                            "expiry_ts_ms",
                            0,
                        )
                        > now_ms
                    )
                ),
                None,
            )

            if market is None:
                stats["states"][market_key] = "WAITING_BOOK"
                print(f"WAITING_BOOK {market_key}: no fresh active market")
                await asyncio.sleep(5)
                continue

            if market.get("slug") == previous_slug:
                stats["states"][market_key] = "WAITING_BOOK"
                print(f"WAITING_BOOK {market_key}: no fresh active market")
                await asyncio.sleep(5)
                continue

            previous_slug = market["slug"]

            metadata = market.get("metadata") or {}
            condition_id = metadata.get("conditionId", market["slug"])

            print(
                f"NEW MARKET {market_key}: "
                f"slug={market['slug']} "
                f"conditionId={condition_id} "
                f"tokens={market['token_ids']}"
            )

            await run_market_session(market_key, market)

            stats["states"][market_key] = "EXPIRED"
            stats["rotations"][market_key] += 1
            stats["latest"].pop(market_key, None)
            stats["metrics"].pop(market_key, None)
            stats["last_valid_book_monotonic"].pop(market_key, None)

            print(
                f"EXPIRED {market_key}: "
                f"slug={market['slug']} "
                f"tokens={market['token_ids']}"
            )

            if market_key == "5m" and stats["rotations"][market_key] >= 2:
                print("5M ROTATION OK")

            if market_key == "15m" and stats["rotations"][market_key] >= 1:
                print("15M ROTATION OK")

    # ==============================================================
    # START COLLECTORS
    # ==============================================================

    binance = BinanceCollector(
        os.getenv("BINANCE_SYMBOL", "btcusdt"),
        on_tick,
    )

    tasks = [
        asyncio.create_task(binance.run(), name="binance"),
        asyncio.create_task(control_output(), name="control-output"),
        asyncio.create_task(rotate_market("5m"), name="rotate-5m"),
        asyncio.create_task(rotate_market("15m"), name="rotate-15m"),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    from app.d5.live import cli
    cli()
