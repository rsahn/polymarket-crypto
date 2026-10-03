"""
Debug PositionSource.read() after route and asset_types fixes.
"""
import sys, asyncio, time, json
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
    clob = GetOnlyTransport("https://clob.polymarket.com",
        frozenset(["/balance-allowance","/data/orders","/data/trades","/time"]),
        headers=auth_headers, pooled=True)
    data = GetOnlyTransport("https://data-api.polymarket.com",
        frozenset(["/positions","/markets","/events","/v2/positions"]))
    rc = ReadOnlyClient(wallet=ACCOUNT, signature_type=3, clob=clob, data=data)

    from app.live.production_readonly import PositionSource
    asset_types = {TOKEN_UP: "CONDITIONAL", TOKEN_DOWN: "CONDITIONAL"}
    pos = PositionSource(rc, wallet=ACCOUNT, asset_types=asset_types,
                         clock=now_ms, collateral_symbol="pUSD", timeout=30)
    result = await pos.read()
    print(f"available={result.get('available')}, reason={result.get('reason')}")
    print(f"balances={result.get('balances')}")

if __name__ == "__main__":
    asyncio.run(main())
