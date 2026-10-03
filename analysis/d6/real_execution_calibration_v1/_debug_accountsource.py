"""
Debug AccountStateSource.read() step by step with timing.
"""
import sys, asyncio, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"
EXCHANGE_V2 = "0xe2222d279d744050d28e00520010520000310f59"

now_ms = lambda: int(time.time() * 1000)


async def main():
    from app.live.l2_existing_reader import load_existing
    creds, report = load_existing(ROOT)
    assert creds is not None

    from polymarket._internal.hmac import build_hmac_signature

    async def async_headers(path):
        ts = int(time.time())
        sig = build_hmac_signature(secret=creds["secret"], timestamp=ts, method="GET", path=path, body=None)
        return {"POLY_ADDRESS": SIGNER, "POLY_API_KEY": creds["apiKey"],
                "POLY_PASSPHRASE": creds["passphrase"], "POLY_SIGNATURE": sig, "POLY_TIMESTAMP": str(ts)}

    from app.live.network_readonly import GetOnlyTransport, ReadOnlyClient
    from app.live.production_readonly import AccountStateSource, plain, units, drain

    clob = GetOnlyTransport(
        "https://clob.polymarket.com",
        frozenset(["/balance-allowance", "/data/orders", "/data/trades"]),
        headers=async_headers,
    )
    rc = ReadOnlyClient(wallet=ACCOUNT, signature_type=3, clob=clob, data=None)

    # Replicate collect() exactly with timing
    started = now_ms()

    # Step 1: wallet check
    print(f"T+{now_ms()-started}ms: wallet check")
    assert str(rc.wallet).lower() == ACCOUNT.lower(), "WALLET_MISMATCH"
    print("  PASS")

    # Step 2: balance-allowance
    t2 = now_ms()
    bal = plain(await rc.get_balance_allowance(asset_type="COLLATERAL"))
    print(f"T+{now_ms()-started}ms (call took {now_ms()-t2}ms): balance-allowance")
    balance = units(bal["balance"])
    allowances = bal["allowances"]
    assert isinstance(allowances, dict), "ALLOWANCE_UNKNOWN"
    matches = [units(v) for k, v in allowances.items() if k.lower() == EXCHANGE_V2.lower()]
    print(f"  matches={len(matches)}")
    assert len(matches) == 1, f"ALLOWANCE_SPENDER_UNKNOWN: {len(matches)}"
    print("  PASS")

    # Step 3: orders
    t3 = now_ms()
    orders = await drain(rc.list_open_orders())
    print(f"T+{now_ms()-started}ms (call took {now_ms()-t3}ms): orders={len(orders)}")
    ids = []
    for order in orders:
        if str(order["maker_address"]).lower() != ACCOUNT.lower():
            print(f"  ORDER_WALLET_MISMATCH: maker={order['maker_address']}")
            raise ValueError("ORDER_WALLET_MISMATCH")
        oid = order["id"]
        if not isinstance(oid, str) or not oid or oid in ids:
            print(f"  ORDER_DUPLICATE_OR_INVALID: id={oid}")
            raise ValueError("ORDER_DUPLICATE_OR_INVALID")
        ids.append(oid)
    print("  PASS")

    # Step 4: trades
    t4 = now_ms()
    trades = await drain(rc.list_account_trades())
    print(f"T+{now_ms()-started}ms (call took {now_ms()-t4}ms): trades={len(trades)}")
    trade_ids = set()
    for trade in trades:
        tid = trade["id"]
        if not isinstance(tid, str) or not tid or tid in trade_ids:
            print(f"  TRADE_DUPLICATE_OR_INVALID: id={tid}")
            raise ValueError("TRADE_DUPLICATE_OR_INVALID")
        trade_ids.add(tid)
        if trade["status"] not in {"CONFIRMED", "FAILED"}:
            print(f"  TRADE_SETTLEMENT_PENDING: status={trade['status']}")
            raise ValueError("TRADE_SETTLEMENT_PENDING")
    print("  PASS")

    # Step 5: fresh guard
    t5 = now_ms()
    age = now_ms() - started
    print(f"T+{age}ms: fresh check (limit=500ms)")
    from app.live.production_readonly import fresh
    from app.live.temporal_contract import ACCOUNT_READ_GUARD_MS
    if not fresh(started, now_ms(), ACCOUNT_READ_GUARD_MS):
        print(f"  FAIL: ACCOUNT_READ_TOO_OLD (age={age}ms > {ACCOUNT_READ_GUARD_MS}ms)")
        raise ValueError("ACCOUNT_READ_TOO_OLD")
    print("  PASS")

    # Step 6: Now run the real AccountStateSource.read()
    print(f"\n--- Real AccountStateSource.read() ---")
    source = AccountStateSource(rc, wallet=ACCOUNT, spender=EXCHANGE_V2,
                                 clock=now_ms, collateral_symbol="pUSD")
    result = await source.read()
    print(f"  available={result.get('available')}, reason={result.get('reason')}")
    print(f"  balance_collateral={result.get('balance_collateral')}")

    print("\n=== DEBUG COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
