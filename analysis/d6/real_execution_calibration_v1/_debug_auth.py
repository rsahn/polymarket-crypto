"""
Debug the full AccountStateSource.read() chain to find exact failure point.
"""
import sys, os, asyncio, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"

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

    clob = GetOnlyTransport(
        "https://clob.polymarket.com",
        frozenset(["/balance-allowance", "/data/orders", "/data/trades"]),
        headers=async_headers,
    )
    rc = ReadOnlyClient(wallet=ACCOUNT, signature_type=3, clob=clob, data=None)

    # Step 1: Direct balance-allowance
    print("Step 1: Direct balance-allowance")
    from app.live.production_readonly import plain
    bal = await rc.get_balance_allowance(asset_type="COLLATERAL")
    p = plain(bal)
    allowances = p["allowances"]
    print(f"  allowance keys: {sorted(allowances.keys())}")
    for k in sorted(allowances.keys()):
        print(f"    {k} (lower: {k.lower()})")

    # Test matching with EXCHANGE_V2
    EXCHANGE_V2 = "0xe2222d279d744050d28e00520010520000310f59"
    print(f"\n  EXCHANGE_V2 lower: {EXCHANGE_V2.lower()}")
    matches = [(k, v) for k, v in allowances.items() if k.lower() == EXCHANGE_V2.lower()]
    print(f"  matches for EXCHANGE_V2: {len(matches)}")
    if matches:
        print(f"  allowance value: {matches[0][1]}")

    # Test matching with EXCHANGE_V1
    EXCHANGE_V1 = "0xe111180000d2663c0091e4f400237545b87b996b"
    matches_v1 = [(k, v) for k, v in allowances.items() if k.lower() == EXCHANGE_V1.lower()]
    print(f"\n  matches for EXCHANGE_V1: {len(matches_v1)}")

    # Step 2: Try list_open_orders directly
    print("\nStep 2: Direct list_open_orders")
    try:
        from polymarket._internal.actions import account as a
        path, params = a.build_list_open_orders_request(cursor=None)
        print(f"  path={path}, params={params}")
        raw = await clob.get_json(path, params=params)
        parsed = a.parse_open_orders_page(raw)
        print(f"  items={len(parsed.items)}, has_more={parsed.has_more}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

    # Step 3: Try list_account_trades directly
    print("\nStep 3: Direct list_account_trades")
    try:
        path2, params2 = a.build_list_account_trades_request(cursor=None)
        print(f"  path={path2}, params={params2}")
        raw2 = await clob.get_json(path2, params=params2)
        parsed2 = a.parse_account_trades_page(raw2)
        print(f"  items={len(parsed2.items)}, has_more={parsed2.has_more}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

    # Step 4: Replicate the exact collect() logic step by step
    print("\nStep 4: Replicate collect() step by step")
    from app.live.production_readonly import plain, units, drain

    # 4a: wallet check
    assert str(rc.wallet).lower() == ACCOUNT.lower(), "WALLET_MISMATCH"
    print("  4a wallet check: PASS")

    # 4b: balance-allowance
    bal = plain(await rc.get_balance_allowance(asset_type="COLLATERAL"))
    print(f"  4b balance-allowance: balance={bal['balance']}")
    balance = units(bal["balance"])
    print(f"  4b units: {balance}")
    allowances = bal["allowances"]
    assert isinstance(allowances, dict), "ALLOWANCE_UNKNOWN"
    print(f"  4b allowances keys: {sorted(allowances.keys())}")

    # 4c: spender matching
    for spender_candidate in [EXCHANGE_V2, EXCHANGE_V1, ACCOUNT]:
        matches = [units(v) for k, v in allowances.items() if k.lower() == spender_candidate.lower()]
        print(f"  4c spender={spender_candidate[:20]}... matches={len(matches)}")

    # 4d: orders
    try:
        orders = await drain(rc.list_open_orders())
        print(f"  4d orders: {len(orders)}")
    except Exception as e:
        print(f"  4d orders FAIL: {type(e).__name__}: {e}")

    # 4e: trades
    try:
        trades = await drain(rc.list_account_trades())
        print(f"  4e trades: {len(trades)}")
    except Exception as e:
        print(f"  4e trades FAIL: {type(e).__name__}: {e}")

    print("\n=== DEBUG COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
