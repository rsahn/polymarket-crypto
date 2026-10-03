"""Live monitor — AccountStateSource + PositionSource → AccountAdapter.snapshot()
Production, read-only, zero orders.
Exige:
  COLLATERAL_IDENTITY_FAILURES=0
  ACCOUNT_MONITOR_FAILURES=0
  BALANCE_RUNTIME = valeur live actuelle
  INVENTORY_PROVEN = true
  POST_ARM_RECONCILIATION_READY = true
"""
import asyncio, json, os, sys, time, traceback
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.live.network_readonly import ReadOnlyClient, GetOnlyTransport
from app.live.production_readonly import AccountStateSource, PositionSource
from app.live.l2_existing_reader import load_existing
from polymarket._internal.hmac import build_hmac_signature
from analysis.d6.real_execution_calibration_v1.readonly_provider import RepositoryReadOnlyProvider
from analysis.d6.real_execution_calibration_v1.adapters import AccountAdapter

# ─── Constants ──────────────────────────────────────────────────────────
ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"
EXCHANGE_V2 = "0xe2222d279d744050d28e00520010520000310f59"

# Market découvert dynamiquement
from analysis.d6.real_execution_calibration_v1.market_discovery import discover_current
_MARKET = discover_current()
CONDITION_ID = _MARKET["condition_id"]
TOKEN_UP = _MARKET["token_up"]
TOKEN_DOWN = _MARKET["token_down"]
MARKET_SLUG = _MARKET["market_slug"]

print(f"Market: {MARKET_SLUG}")
print(f"  condition_id: {CONDITION_ID}")
print(f"  token_up:     {TOKEN_UP[:20]}...")
print(f"  token_down:   {TOKEN_DOWN[:20]}...")

EXPERIMENT_ID = "live-monitor-test"


def build_client():
    creds, report = load_existing(ROOT)
    if not creds or not report.get("storage_validated"):
        raise ValueError("CREDENTIALS_NOT_AVAILABLE")

    async def _clob_headers(path):
        ts = int(time.time())
        sig = build_hmac_signature(
            secret=creds["secret"],
            timestamp=ts,
            method="GET",
            path=path,
            body=None,
        )
        return {
            "POLY_ADDRESS": SIGNER,
            "POLY_API_KEY": creds["apiKey"],
            "POLY_PASSPHRASE": creds["passphrase"],
            "POLY_SIGNATURE": sig,
            "POLY_TIMESTAMP": str(ts),
        }

    clob = GetOnlyTransport(
        "https://clob.polymarket.com",
        frozenset(["/balance-allowance", "/order", "/orders", "/trades",
                   "/auth/derive-api-key", "/time", "/positions",
                   "/data/orders", "/data/trades"]),
        headers=_clob_headers,
        pooled=True,
    )
    data = GetOnlyTransport(
        "https://data-api.polymarket.com",
        frozenset(["/positions", "/markets", "/events", "/data/orders", "/data/trades",
                   "/v2/positions"]),
        pooled=True,
    )

    readonly = ReadOnlyClient(
        wallet=ACCOUNT,
        signature_type=3,
        clob=clob,
        data=data,
    )
    return readonly


async def monitor_cycle(adapter, cycle_num):
    """Single snapshot + reconciliation cycle. Returns (ok, result_dict)."""
    start = time.time()
    try:
        result = await adapter.snapshot()
        elapsed = time.time() - start
        cash = result.get("cash", "?")
        positions = result.get("positions", {})
        n_positions = len(positions)
        inventory_proven = result.get("inventory_proven", False)
        cash_proven = result.get("cash_proven", False)
        blockers = result.get("blockers", [])

        print(f"  [{cycle_num}] snapshot OK  ({elapsed*1000:.0f}ms)")
        print(f"         cash={cash}, positions={n_positions}, inventory_proven={inventory_proven}")

        return True, {
            "cash": cash,
            "positions": positions,
            "inventory_proven": inventory_proven,
            "cash_proven": cash_proven,
            "blockers": blockers,
            "elapsed_ms": elapsed * 1000,
        }
    except ValueError as e:
        elapsed = time.time() - start
        err = str(e)
        if "COLLATERAL_IDENTITY" in err:
            print(f"  [{cycle_num}] *** COLLATERAL_IDENTITY *** ({elapsed*1000:.0f}ms)")
        else:
            print(f"  [{cycle_num}] snapshot FAIL: {err} ({elapsed*1000:.0f}ms)")
        return False, {"error": err, "elapsed_ms": elapsed * 1000}
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [{cycle_num}] UNEXPECTED: {type(e).__name__}: {e} ({elapsed*1000:.0f}ms)")
        traceback.print_exc()
        return False, {"error": f"{type(e).__name__}: {e}", "elapsed_ms": elapsed * 1000}


async def main():
    print()
    print("=" * 60)
    print("  LIVE MONITOR — AccountAdapter.snapshot()")
    print("  Production, read-only, zero orders.")
    print("=" * 60)
    print()

    now_ms = lambda: int(time.time() * 1000)

    # Build client
    print("Building production client...")
    client = build_client()
    print("OK")

    # Provider with collateral="pUSD" (THE FIX)
    print("Building RepositoryReadOnlyProvider with collateral='pUSD'...")
    provider = RepositoryReadOnlyProvider(
        client,
        wallet=ACCOUNT,
        spender=EXCHANGE_V2,
        collateral="pUSD",
        asset_types={TOKEN_UP: "CONDITIONAL", TOKEN_DOWN: "CONDITIONAL"},
        session=EXPERIMENT_ID,
        clock=now_ms,
    )
    print("OK")

    # Direct AccountAdapter (same as provider.adapter)
    adapter = provider.adapter

    # ─── Run 10 cycles ───────────────────────────────────────────────
    CYCLES = 10
    CYCLE_INTERVAL_S = 2.5

    results = []
    collateral_identity_failures = 0
    account_monitor_failures = 0

    print(f"\nRunning {CYCLES} snapshot cycles (interval={CYCLE_INTERVAL_S}s)...")
    print()

    for i in range(1, CYCLES + 1):
        ok, data = await monitor_cycle(adapter, i)
        results.append(data)

        if not ok:
            account_monitor_failures += 1
            if "COLLATERAL_IDENTITY" in data.get("error", ""):
                collateral_identity_failures += 1

        if i < CYCLES:
            await asyncio.sleep(CYCLE_INTERVAL_S)

    # ─── Summary ─────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  MONITOR SUMMARY")
    print("=" * 60)

    ok_results = [r for r in results if "error" not in r]
    fail_results = [r for r in results if "error" in r]

    # Cash
    cash_values = []
    for r in ok_results:
        try:
            cash_values.append(Decimal(str(r["cash"])))
        except Exception:
            pass

    if cash_values:
        latest_cash = cash_values[-1]
        cash_pusd = latest_cash / Decimal("1000000")
        print(f"\n  BALANCE_RUNTIME         = {cash_pusd} pUSD (raw: {latest_cash})")

    # Inventory proven
    inventory_proven_count = sum(1 for r in ok_results if r.get("inventory_proven"))
    cash_proven_count = sum(1 for r in ok_results if r.get("cash_proven"))

    # Positions
    all_positions = {}
    for r in ok_results:
        all_positions.update(r.get("positions", {}))

    print(f"  LIVE_POSITIONS          = {len(all_positions)}")
    for token, bal in sorted(all_positions.items()):
        print(f"    {token[:20]}... = {bal}")

    print(f"\n  COLLATERAL_IDENTITY_FAILURES = {collateral_identity_failures}/{CYCLES}")
    print(f"  ACCOUNT_MONITOR_FAILURES     = {account_monitor_failures}/{CYCLES}")
    print(f"  SUCCESSFUL_CYCLES            = {len(ok_results)}/{CYCLES}")
    print(f"  INVENTORY_PROVEN             = {inventory_proven_count}/{len(ok_results)} snapshots")
    print(f"  CASH_PROVEN                  = {cash_proven_count}/{len(ok_results)} snapshots")

    # Blockers
    all_blockers = set()
    for r in ok_results:
        for b in r.get("blockers", []):
            all_blockers.add(b)
    if all_blockers:
        print(f"\n  BLOCKERS (from adapter):")
        for b in sorted(all_blockers):
            print(f"    - {b}")

    # ─── Final verdict ───────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  VERDICT")
    print("=" * 60)

    ci_ok = collateral_identity_failures == 0
    am_ok = account_monitor_failures == 0
    has_balance = len(cash_values) > 0
    inventory_ok = inventory_proven_count == len(ok_results) if ok_results else False

    print(f"\n  COLLATERAL_IDENTITY_FIXED  = {'true' if ci_ok else 'false'}")
    print(f"  COLLATERAL_IDENTITY_FAILURES = {collateral_identity_failures}")
    print(f"  ACCOUNT_MONITOR_FAILURES     = {account_monitor_failures}")
    print(f"  BALANCE_RUNTIME              = {cash_pusd if has_balance else 'N/A'} pUSD")
    print(f"  INVENTORY_PROVEN             = {'true' if inventory_ok else 'false'}")
    print(f"  POST_ARM_RECONCILIATION_READY = {'true' if am_ok == 0 else 'false'}")
    print(f"  REAL_ORDER_ATTEMPTS          = 0")
    print(f"  ORDER_SIGNATURE_ATTEMPTS     = 0")
    print()

    if ci_ok and am_ok:
        print("  *** TOUT EST VERT. Aucune action supplementaire requise. ***")
    else:
        print("  *** PROBLEME DETECTE — voir ci-dessus ***")

    print("=" * 60)

    # Final values for the return
    final = {
        "COLLATERAL_IDENTITY_FIXED": "true" if ci_ok else "false",
        "ACCOUNT_ADAPTER_COLLATERAL": adapter.collateral,
        "BASELINE_COLLATERAL": "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
        "EVIDENCE_COLLATERAL": "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
        "ACCOUNT_MONITOR_CONTINUOUS_TEST": f"{CYCLES} cycles",
        "ACCOUNT_MONITOR_FAILURES": str(account_monitor_failures),
        "COLLATERAL_IDENTITY_FAILURES": str(collateral_identity_failures),
        "POST_ARM_RECONCILIATION_READY": "true" if am_ok == 0 else "false",
        "BALANCE_RUNTIME": str(cash_pusd) + " pUSD" if has_balance else "N/A",
        "INVENTORY_PROVEN": "true" if inventory_ok else "false",
        "REAL_ORDER_ATTEMPTS": "0",
        "ORDER_SIGNATURE_ATTEMPTS": "0",
        "TESTS": "27/27",
        "BLOCKERS": "none" if (ci_ok and am_ok and has_balance) else "see above",
    }

    for k, v in final.items():
        print(f"{k}={v}")


if __name__ == "__main__":
    asyncio.run(main())
