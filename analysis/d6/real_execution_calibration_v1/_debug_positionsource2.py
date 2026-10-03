"""
Deep debug of PositionSource.read() - trace exact exception.
"""
import sys, asyncio, time, json, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"
now_ms = lambda: int(time.time() * 1000)

from analysis.d6.real_execution_calibration_v1.market_discovery import discover_current
market = discover_current()
TOKEN_UP = market["token_up"]
TOKEN_DOWN = market["token_down"]

async def main():
    from app.live.l2_existing_reader import load_existing
    creds, report = load_existing(ROOT)
    from polymarket._internal.hmac import build_hmac_signature

    async def auth_headers(path):
        ts = int(time.time())
        sig = build_hmac_signature(secret=creds["secret"], timestamp=ts, method="GET", path=path, body=None)
        return {"POLY_ADDRESS": SIGNER, "POLY_API_KEY": creds["apiKey"],
                "POLY_PASSPHRASE": creds["passphrase"],
                "POLY_SIGNATURE": sig, "POLY_TIMESTAMP": str(ts)}

    from app.live.network_readonly import GetOnlyTransport, ReadOnlyClient
    from app.live.production_readonly import drain, plain

    clob = GetOnlyTransport("https://clob.polymarket.com",
        frozenset(["/balance-allowance","/data/orders","/data/trades","/time"]),
        headers=auth_headers, pooled=True)
    data = GetOnlyTransport("https://data-api.polymarket.com",
        frozenset(["/positions","/markets","/events","/v2/positions"]))
    rc = ReadOnlyClient(wallet=ACCOUNT, signature_type=3, clob=clob, data=data)

    started = now_ms()

    # Step 1: list_positions via paginator
    print("Step 1: list_positions")
    try:
        paginator = rc.list_positions(user=ACCOUNT, full_history=True,
            include_archived=True, filter_type="TOKENS", filter_amount=0)
        rows = await drain(paginator, max_pages=100, max_items=10000)
        print(f"  rows={len(rows)}")
        for r in rows:
            print(f"  {json.dumps({k:str(v) if not isinstance(v,(str,int,float,bool)) else v for k,v in r.items()})[:200]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        rows = []

    # Step 2: check balances for each token
    print(f"\nStep 2: balance-allowance for tokens")
    for token_name, token_id in [("UP", TOKEN_UP), ("DOWN", TOKEN_DOWN)]:
        try:
            bal = plain(await rc.get_balance_allowance(asset_type="CONDITIONAL", token_id=token_id))
            print(f"  {token_name} ({token_id[:20]}...): balance={bal['balance']}")
        except Exception as e:
            print(f"  {token_name} ({token_id[:20]}...): FAIL {type(e).__name__}: {e}")

    # Step 3: Replicate the exact PositionSource collect() logic
    print(f"\nStep 3: replicate PositionSource collect()")
    try:
        assert str(rc.wallet).lower() == ACCOUNT.lower()
        print("  wallet check: PASS")

        paginator = rc.list_positions(user=ACCOUNT, full_history=True,
            include_archived=True, filter_type="TOKENS", filter_amount=0)
        rows = await drain(paginator, max_pages=100, max_items=10000)
        print(f"  drain rows: {len(rows)}")

        balances = {}
        for row in rows:
            if str(row["wallet"]).lower() != ACCOUNT.lower():
                print(f"  POSITION_WALLET_MISMATCH")
                raise ValueError("POSITION_WALLET_MISMATCH")
            token = str(row["asset_id"])
            from decimal import Decimal
            size = Decimal(str(row["current_size"]))
            if size < 0 or token in balances:
                print(f"  INVALID_POSITION: token={token}, size={size}")
                raise ValueError("INVALID_POSITION")
            balances[token] = size

        print(f"  position balances from list: {balances}")

        asset_types = {TOKEN_UP: "CONDITIONAL", TOKEN_DOWN: "CONDITIONAL"}
        for token in set(balances) | set(asset_types):
            asset_type = asset_types.get(token)
            if asset_type not in {"CONDITIONAL", "CONDITIONAL-V2"}:
                print(f"  ASSET_TYPE_UNKNOWN: token={token}, asset_type={asset_type}")
                raise ValueError("ASSET_TYPE_UNKNOWN")

            print(f"  checking balance for token {token[:20]}... (asset_type={asset_type})")
            bal = plain(await rc.get_balance_allowance(asset_type=asset_type, token_id=token))
            from app.live.production_readonly import units
            held = units(bal["balance"])
            if token in balances and balances[token] != held:
                print(f"  INVENTORY_MISMATCH: token={token[:20]}..., list={balances[token]}, onchain={held}")
                raise ValueError("INVENTORY_MISMATCH")
            if token not in balances and held != 0:
                print(f"  INDEXER_MISSING_INVENTORY: token={token[:20]}..., held={held}")
                raise ValueError("INDEXER_MISSING_INVENTORY")
            balances[token] = held
            print(f"    -> balance={held}")

        from app.live.temporal_contract import POSITIONS_READ_GUARD_MS
        from app.live.production_readonly import fresh
        if not fresh(started, now_ms(), POSITIONS_READ_GUARD_MS):
            print(f"  POSITIONS_TOO_OLD: elapsed={now_ms()-started}ms > {POSITIONS_READ_GUARD_MS}ms")
            raise ValueError("POSITIONS_TOO_OLD")

        print(f"  SUCCESS: balances={balances}")
    except Exception as e:
        print(f"  FAIL at step 3: {type(e).__name__}: {e}")
        traceback.print_exc()

    print(f"\nTotal elapsed: {now_ms()-started}ms")

if __name__ == "__main__":
    asyncio.run(main())
