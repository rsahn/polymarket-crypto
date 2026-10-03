"""Debug: test BookAdapter isolation."""
import asyncio, sys, time
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"C:\Users\Ramy\Documents\polymarket-crypto")
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from analysis.d6.real_execution_calibration_v1.adapters import BookAdapter

TOKEN_UP = "44191601964933458390"
TOKEN_DOWN = "10823440926225660160"
CONDITION_ID = "0xd79fc467310db39774c3132e459190f6d6df6a695a4cb2d5eee8a006ec0faaf7"
MARKET_SLUG = "btc-updown-5m-1790689800"
now_ms = lambda: int(time.time() * 1000)


class TestStream:
    def read(self):
        now = now_ms()
        r = dict(
            available=True,
            book_synced=True,
            connected=True,
            synchronized=True,
            fresh=True,
            generation=1,
            market=MARKET_SLUG,
            condition=CONDITION_ID,
            books={
                TOKEN_UP: dict(
                    bids=[(Decimal("0.45"), Decimal("100"))],
                    asks=[(Decimal("0.46"), Decimal("100"))],
                    observed_ms=now,
                    book_state_id="test-001",
                ),
                TOKEN_DOWN: dict(
                    bids=[(Decimal("0.45"), Decimal("100"))],
                    asks=[(Decimal("0.46"), Decimal("100"))],
                    observed_ms=now,
                    book_state_id="test-002",
                ),
            },
            observed_ms=now,
        )
        print(f"  [DEBUG] read() called: available={r['available']}", flush=True)
        return r

    async def run(self, **kwargs):
        print("  [DEBUG] stream.run() started", flush=True)
        if "rest_seed_coro" in kwargs:
            print("  [DEBUG] rest_seed_coro provided, calling it", flush=True)
            try:
                await kwargs["rest_seed_coro"]()
                print("  [DEBUG] rest_seed_coro completed", flush=True)
            except Exception as e:
                print(f"  [DEBUG] rest_seed_coro failed: {e}", flush=True)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            print("  [DEBUG] stream.run() cancelled", flush=True)

    @property
    def condition(self):
        return CONDITION_ID


async def test():
    stream = TestStream()
    book = BookAdapter(
        stream,
        market=CONDITION_ID,
        tokens={"UP": TOKEN_UP, "DOWN": TOKEN_DOWN},
        clock=now_ms,
    )

    def status(s):
        print(f"  [DEBUG] book status: {s}", flush=True)

    book_task = asyncio.create_task(book.run(status))
    await asyncio.sleep(0.5)

    print(f"  [DEBUG] state before wait_ready: {book.state}", flush=True)
    print(f"  [DEBUG] ready.is_set(): {book.ready.is_set()}", flush=True)
    print(f"  [DEBUG] book_task.done(): {book_task.done()}", flush=True)
    if book_task.done():
        try:
            book_task.result()
        except Exception as e:
            print(f"  [DEBUG] book_task exception: {e}", flush=True)

    try:
        await book.wait_ready(timeout=10)
        print(f"  [DEBUG] wait_ready succeeded! state={book.state}", flush=True)
    except Exception as e:
        print(f"  [DEBUG] wait_ready failed: {e}", flush=True)

    book_task.cancel()
    await asyncio.sleep(0.1)
    print("  [DEBUG] done", flush=True)


asyncio.run(test())
