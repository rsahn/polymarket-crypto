"""
Freshest read: positions, balances, orders, trades.
"""
import sys, asyncio, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"

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
    clob = GetOnlyTransport("https://clob.polymarket.com",
        frozenset(["/balance-allowance", "/data/orders", "/data/trades", "/time"]),
        headers=auth_headers, pooled=True)
    data = GetOnlyTransport("https://data-api.polymarket.com",
        frozenset(["/positions", "/markets", "/events", "/v2/positions"]),
        pooled=True)
    rc = ReadOnlyClient(wallet=ACCOUNT, signature_type=3, clob=clob, data=data)

    from app.live.production_readonly import drain, plain

    # 1. Balance
    bal = plain(await rc.get_balance_allowance(asset_type="COLLATERAL"))
    print(f"BALANCE: {bal['balance']} raw, allowances={bal['allowances']}")

    # 2. Orders
    orders = await drain(rc.list_open_orders())
    print(f"ORDERS: {len(orders)}")

    # 3. Trades
    trades = await drain(rc.list_account_trades())
    print(f"TRADES: {len(trades)}")

    # 4. Positions from Data API
    paginator = rc.list_positions(user=ACCOUNT, full_history=True,
        include_archived=True, filter_type="TOKENS", filter_amount=0)
    rows = await drain(paginator, max_pages=100, max_items=10000)
    print(f"POSITIONS (Data API): {len(rows)}")

    # 5. Discovered market
    from analysis.d6.real_execution_calibration_v1.market_discovery import discover_current
    market = discover_current()
    TOKEN_UP = market["token_up"]
    TOKEN_DOWN = market["token_down"]
    print(f"MARKET: {market['market_slug']}")
    print(f"CONDITION: {market['condition_id']}")

    # 6. On-chain token balances
    for name, token_id in [("UP", TOKEN_UP), ("DOWN", TOKEN_DOWN)]:
        bal2 = plain(await rc.get_balance_allowance(asset_type="CONDITIONAL", token_id=token_id))
        print(f"  {name} token={token_id[:24]}... onchain={bal2['balance']}")

    if rows:
        for r in rows:
            safe = {}
            for k, v in r.items():
                if isinstance(v, (str, int, float, bool)):
                    safe[k] = v
                elif v is None:
                    safe[k] = None
                else:
                    safe[k] = str(v)
            print(f"  POS: {json.dumps(safe)}")

if __name__ == "__main__":
    asyncio.run(main())
