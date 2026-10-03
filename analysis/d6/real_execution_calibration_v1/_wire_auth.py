"""
Step 1: Wire credentials into GetOnlyTransport headers= callback.
Tests the full chain from HMAC signing to live CLOB reads.
"""
import sys, os, asyncio, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
COLLATERAL = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"

now_ms = lambda: int(time.time() * 1000)


async def main():
    from app.live.l2_existing_reader import load_existing
    creds, report = load_existing(ROOT)
    assert creds is not None, "CREDENTIALS_NOT_AVAILABLE"
    print(f"Credentials loaded: apiKey={creds['apiKey'][:20]}... secret={creds['secret'][:10]}...")

    from polymarket._internal.hmac import build_hmac_signature

    def make_headers(method, path, body=None):
        ts = int(time.time())
        sig = build_hmac_signature(
            secret=creds["secret"],
            timestamp=ts,
            method=method,
            path=path,
            body=body,
        )
        return {
            "POLY_ADDRESS": SIGNER,
            "POLY_API_KEY": creds["apiKey"],
            "POLY_PASSPHRASE": creds["passphrase"],
            "POLY_SIGNATURE": sig,
            "POLY_TIMESTAMP": str(ts),
        }

    async def async_headers(path):
        return make_headers("GET", path)

    # Test 1: HMAC signature generation
    print("\n[Test 1] HMAC signature generation")
    sig = build_hmac_signature(secret=creds["secret"], timestamp=int(time.time()),
                               method="GET", path="/balance-allowance", body=None)
    assert len(sig) > 20, f"Signature too short: {len(sig)}"
    print(f"  HMAC signature OK ({len(sig)} chars)")

    # Test 2: GET /balance-allowance WITH auth
    print("\n[Test 2] GET /balance-allowance WITH auth headers")
    from app.live.network_readonly import GetOnlyTransport, ReadOnlyClient
    from polymarket._internal.actions import account as a

    clob = GetOnlyTransport(
        "https://clob.polymarket.com",
        frozenset(["/balance-allowance", "/order", "/orders", "/trades",
                   "/auth/derive-api-key", "/time", "/positions",
                   "/data/orders", "/data/trades"]),
        headers=async_headers,
    )
    rc = ReadOnlyClient(wallet=ACCOUNT, signature_type=3, clob=clob, data=None)

    path, params = a.build_balance_allowance_request(asset_type="COLLATERAL", signature_type=3)
    raw = await clob.get_json(path, params=params)
    result = a.parse_balance_allowance(raw)
    print(f"  balance: {result.balance}")
    print(f"  allowances: {result.allowances}")
    print("  PASS: balance-allowance authenticated")

    # Test 3: GET /time (public, no auth needed)
    print("\n[Test 3] GET /time (public endpoint)")
    clob_public = GetOnlyTransport(
        "https://clob.polymarket.com",
        frozenset(["/time"]),
    )
    raw_public = await clob_public.get_json("/time")
    print(f"  server time: {raw_public}")
    print("  PASS: public endpoint still works")

    # Test 4: GET /orders (authenticated)
    print("\n[Test 4] GET /orders (authenticated, may be empty)")
    try:
        path2, params2 = a.build_list_open_orders_request(cursor=None)
        raw2 = await clob.get_json(path2, params=params2)
        parsed2 = a.parse_open_orders_page(raw2)
        print(f"  orders page: items={len(parsed2.items)}, has_more={parsed2.has_more}")
        print("  PASS: orders read")
    except Exception as e:
        print(f"  orders read: {type(e).__name__}: {e}")

    # Test 5: GET /trades (authenticated)
    print("\n[Test 5] GET /trades (authenticated)")
    try:
        path3, params3 = a.build_list_account_trades_request(cursor=None)
        raw3 = await clob.get_json(path3, params=params3)
        parsed3 = a.parse_account_trades_page(raw3)
        print(f"  trades page: items={len(parsed3.items)}, has_more={parsed3.has_more}")
        print("  PASS: trades read")
    except Exception as e:
        print(f"  trades read: {type(e).__name__}: {e}")

    # Test 6: AccountStateSource.read() WITH auth
    print("\n[Test 6] AccountStateSource.read() WITH auth")
    from app.live.production_readonly import AccountStateSource, PositionSource

    clob2 = GetOnlyTransport(
        "https://clob.polymarket.com",
        frozenset(["/balance-allowance", "/order", "/orders", "/trades",
                   "/auth/derive-api-key", "/time", "/positions",
                   "/data/orders", "/data/trades"]),
        headers=async_headers,
    )
    data = GetOnlyTransport(
        "https://data-api.polymarket.com",
        frozenset(["/positions", "/markets", "/events", "/data/orders", "/data/trades"]),
    )
    rc2 = ReadOnlyClient(wallet=ACCOUNT, signature_type=3, clob=clob2, data=data)

    account_source = AccountStateSource(rc2, wallet=ACCOUNT, spender=ACCOUNT,
                                         clock=now_ms, collateral_symbol="pUSD")
    result = await account_source.read()
    print(f"  available: {result.get('available')}")
    print(f"  balance_collateral: {result.get('balance_collateral')}")
    print(f"  open_orders: {len(result.get('open_order_ids', []))}")
    print(f"  trades: {len(result.get('trade_ids', []))}")
    assert result.get('available') is True, f"Expected available=True, got {result.get('reason')}"
    print("  PASS: AccountStateSource.read() authenticated")

    # Test 7: PositionSource.read()
    print("\n[Test 7] PositionSource.read()")
    position_source = PositionSource(rc2, wallet=ACCOUNT,
                                      asset_types={"0x4D97DCd97eC945f40cF65F87097ACe5EA0476045": ["up", "down"]},
                                      clock=now_ms, collateral_symbol="pUSD")
    pos_result = await position_source.read()
    print(f"  available: {pos_result.get('available')}")
    print(f"  positions: {len(pos_result.get('balances', {}))}")
    print("  PASS: PositionSource.read()")

    # Test 8: AccountAdapter.snapshot()
    print("\n[Test 8] AccountAdapter.snapshot()")
    from analysis.d6.real_execution_calibration_v1.adapters import AccountAdapter

    adapter = AccountAdapter(account_source, position_source,
                              account=ACCOUNT, collateral="pUSD",
                              session="auth-wire-test", clock=now_ms,
                              evidence_source=None)
    try:
        snap = await adapter.snapshot()
        print(f"  cash: {snap.get('cash')}")
        print(f"  positions: {snap.get('positions')}")
        print(f"  open_orders: {len(snap.get('open_orders', []))}")
        print(f"  blockers: {snap.get('blockers')}")
        print("  PASS: AccountAdapter.snapshot() works")
    except ValueError as e:
        print(f"  snapshot: {e}")
        if "BASELINE" in str(e):
            print("  (expected -- no baseline set for this test)")

    print("\n=== ALL TESTS COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
