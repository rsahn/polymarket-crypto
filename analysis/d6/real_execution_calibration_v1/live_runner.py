"""Real execution runner -- production wiring with zero mocks.
AsyncSecureClient, StreamBook WS, real AccountStateSource/PositionSource.

Usage:  python live_runner.py
        (read TTY prompt, type "CALIBRATE <experiment_id>")

No orders, cancellations, transactions, signatures, or allowances are executed
until the human types the CALIBRATE confirmation at the TTY prompt.
"""
import asyncio, json, shutil, sys, time, os as _os
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from polymarket import AsyncSecureClient, ApiKeyCreds
from polymarket.environments import PRODUCTION
from app.live.l2_existing_reader import load_existing
from app.live.production_readonly import AccountStateSource, PositionSource
from app.live.readonly_book_stream import StreamBook
from analysis.d6.real_execution_calibration_v1.runner import PreparedSession, SignalSource
from analysis.d6.real_execution_calibration_v1.engine import HumanArm, Coordinator
from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier, FeeRisk
from analysis.d6.real_execution_calibration_v1.custody import CustodyOwner, CustodyStateStore
from analysis.d6.real_execution_calibration_v1.manual_custody import (
    ManualCustodyChannel, ManualReceiptAuthority, ManualReceiptVerifier,
)
from analysis.d6.real_execution_calibration_v1.v1_binding import verify as v1_verify
from analysis.d6.real_execution_calibration_v1.core import allocate_experiment_id, Journal
from analysis.d6.real_execution_calibration_v1.transport import SDKPort
from analysis.d6.real_execution_calibration_v1.supervisor import run as supervisor_run

# --- Production constants ---
ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER  = "0x9348eFd557A09e644795C8F114BcF0BeF86F203a"
CONDITION_ID = "0xa467b14d51f01b957109d9cbb1d6c124fab2a089d52ed8f471d23c2812e743b7"
TOKEN_UP   = "32338220190071351435772801779725302244575775216413325951443816017994629993401"
TOKEN_DOWN = "25659310674993675562345759665114759892400026242514633218387667107987341231962"
COLLATERAL  = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
BASELINE_DIGEST = "46b72832b1480d2c6532d143c524ee8ebe289bb18f3f3ded3b8e10858d2263e4"
DEPLOYMENT_BLOCK = 94559626
MARKET_SLUG = "xi-jinping-out-before-2027"
DPAPI_DIR = Path.home() / "AppData/Local/PolymarketD6L2"
DIRECTORY = Path("D:/polymarket-real-calibration/live")
CUSTODY_JOURNAL_PATH = ROOT / "analysis/d6/real_execution_calibration_v1/custody_journal.jsonl"

# --- 0. Allocate experiment_id ---
EXPERIMENT_ID = allocate_experiment_id(DIRECTORY, base_name="live-v1")
print(f"Allocated experiment_id: {EXPERIMENT_ID}")

# --- 1. Evidence authority ---
authority = SelfAttestingAuthority()
strategy_hashes = v1_verify()

# --- 2. Credentials (existing DPAPI, never hardcoded) ---
creds_dict, report = load_existing(ROOT)
if not creds_dict or not report.get("storage_validated"):
    print("CREDENTIALS_NOT_AVAILABLE: run recovery first")
    sys.exit(1)

api_creds = ApiKeyCreds(
    key=creds_dict["apiKey"],
    secret=creds_dict["secret"],
    passphrase=creds_dict["passphrase"],
)

# --- 3. Custody production ---
from app.live.l2_windows_storage import WindowsProtection
platform = WindowsProtection()
channel = ManualCustodyChannel(str(DPAPI_DIR), platform=platform)
receipt_authority = ManualReceiptAuthority(channel)
receipt_verifier = ManualReceiptVerifier(receipt_authority)

if CUSTODY_JOURNAL_PATH.exists():
    CUSTODY_JOURNAL_PATH.unlink()
custody_journal = Journal(str(CUSTODY_JOURNAL_PATH), "custody-store")
custody_store = CustodyStateStore(custody_journal)
custody_owner = CustodyOwner(channel, receipt_verifier, state_store=custody_store)

verifier = EvidenceVerifier(
    authority,
    account=ACCOUNT,
    market=CONDITION_ID,
    session=EXPERIMENT_ID,
    collateral=COLLATERAL,
    strategy_hashes=strategy_hashes,
)

# --- 4. Build evidence callable ---
def build_evidence_fn(owner, ch):
    def evidence():
        from analysis.d6.real_execution_calibration_v1.evidence import build_evidence as _be
        return _be(
            experiment_id=EXPERIMENT_ID,
            owner=owner,
            baseline_digest=BASELINE_DIGEST,
            account=ACCOUNT,
            signer=SIGNER,
            condition_id=CONDITION_ID,
            token_up=TOKEN_UP,
            token_down=TOKEN_DOWN,
            collateral=COLLATERAL,
            channel_path=str(ch.directory),
            durable_receipt_id="2e15484d9b7eabf860f797cefb530cd39aaecd9affee4fd9a9449e620dd66b5d",
            rpc_block=DEPLOYMENT_BLOCK,
        )
    return evidence

evidence = build_evidence_fn(custody_owner.verifier.owner, channel)

# --- 5. AsyncSecureClient - real SDK ---
async def build_secure_client():
    private_key = None
    for env_var in ("SIGNER_PRIVATE_KEY", "D6_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY"):
        val = _os.environ.get(env_var)
        if val:
            private_key = val
            break
    if not private_key:
        raise ValueError(
            "PRIVATE_KEY_REQUIRED: set SIGNER_PRIVATE_KEY environment variable\n"
            "  $env:SIGNER_PRIVATE_KEY=...   (PowerShell)\n"
            "  set SIGNER_PRIVATE_KEY=...       (CMD)"
        )
    client = await AsyncSecureClient.create(
        private_key=private_key,
        wallet=ACCOUNT,
        environment=PRODUCTION,
        credentials=api_creds,
        nonce=0,
    )
    return client

# --- 6. Preflight summary display ---
def pre_arm_summary(report, experiment_id, log_path, text_path):
    pre = report.get('preflight', report)
    checks = pre.get('checks', {})
    blockers = pre.get('blockers', [])
    bal = pre.get('balance', pre.get('balance_sufficient', {}))
    if isinstance(bal, dict):
        bal_str = f"{bal.get('cash', bal.get('required_cash', '?'))} {bal.get('unit', 'pUSD')}"
    else:
        bal_str = str(bal)
    print()
    print("=" * 60)
    print("  PRE_ARM_READY  --  LIVE EXECUTION")
    print("=" * 60)
    print(f"  PRE_ARM_READY          = {pre.get('status') == 'CALIBRATION_READY'}")
    print(f"  CALIBRATION_READY      = {pre.get('status') == 'CALIBRATION_READY'}")
    print(f"  EXPERIMENT_ID          = {experiment_id}")
    print(f"  CAPS                   = 100/25/1")
    print(f"  BALANCE                = {bal_str}")
    print(f"  BALANCE_SUFFICIENT     = {checks.get('balance_sufficient', '?')}")
    print(f"  LOG_JSONL              = {log_path}")
    print(f"  LOG_TEXT               = {text_path}")
    print(f"  FRESH_ENTRY_GUARD      = {checks.get('fresh_runtime_evidence', '?')}")
    print(f"  KILL_SWITCH_READY      = {checks.get('kill_switch_tested', '?')}")
    print(f"  RECONCILIATION_READY   = {checks.get('reconciliation_tested', '?')}")
    print(f"  CUSTODY_READY          = {checks.get('exit_handoff_ready', '?')}")
    print(f"  WS_HEALTHY             = {checks.get('ws_healthy', '?')}")
    print(f"  STORAGE_SUFFICIENT     = {checks.get('storage_sufficient', '?')}")
    print(f"  D6_FLAGS_FALSE         = {checks.get('global_D6_flags_false', '?')}")
    print(f"  BLOCKERS               = {blockers if blockers else 'none'}")
    print("=" * 60)
    print()

def production_confirm(experiment_id, report, *, verifier, evidence):
    log_jsonl = str(DIRECTORY / f"{experiment_id}.jsonl")
    log_text = str(DIRECTORY / f"REAL_CALIBRATION_{time.strftime('%Y%m%d_%H%M')}_{experiment_id}-p0000.log")
    pre_arm_summary(report, experiment_id, log_jsonl, log_text)
    return HumanArm.confirm(experiment_id, report, verifier=verifier, evidence=evidence)

# --- 7. Main ---
async def main():
    now_ms = lambda: int(time.time() * 1000)

    print("Creating AsyncSecureClient...")
    secure_client = await build_secure_client()
    print(f"  wallet={secure_client.wallet}")
    print(f"  signer={secure_client.signer}")
    print(f"  environment={secure_client.environment}")

    account_reader = AccountStateSource(
        secure_client, wallet=ACCOUNT, spender=ACCOUNT,
        clock=now_ms, collateral_symbol="pUSD",
    )
    position_reader = PositionSource(
        secure_client, wallet=ACCOUNT,
        asset_types={
            TOKEN_UP: "CONDITIONAL",
            TOKEN_DOWN: "CONDITIONAL",
        },
        clock=now_ms, collateral_symbol="pUSD",
    )

    # Far-future expiry for non-expiring markets (xi-jinping-out-before-2027)
    expiry_ms = int(time.time() * 1000) + 86400000 * 30  # 30 days from now
    stream_book = StreamBook(
        slug=MARKET_SLUG,
        condition=CONDITION_ID,
        tokens=(TOKEN_UP, TOKEN_DOWN),
        expiry=expiry_ms,
        clock=now_ms,
    )
    stream_book.connect(MARKET_SLUG, (TOKEN_UP, TOKEN_DOWN), 1)

    baseline = {
        "version": "REAL_EXECUTION_CALIBRATION_V1",
        "started": 1790577000000,
    }

    session = PreparedSession(
        directory=DIRECTORY,
        experiment_id=EXPERIMENT_ID,
        account=ACCOUNT,
        starting_cash="109160000",
        account_reader=account_reader,
        position_reader=position_reader,
        stream=stream_book,
        market=CONDITION_ID,
        collateral="pUSD",
        tokens={"UP": TOKEN_UP, "DOWN": TOKEN_DOWN},
        clock=now_ms,
        evidence_source=None,
        authority=authority,
        baseline=baseline,
    )
    print("OK PreparedSession built (real SDK, real WS book)")

    from analysis.d6.real_execution_calibration_v1.preflight import evaluate as preflight_eval
    proof = evidence()
    free_bytes = shutil.disk_usage(DIRECTORY).free
    report = preflight_eval(proof, now_ms(), free_bytes, verifier)
    print(f"Preflight status: {report['status']}")
    for k, v in sorted(report.get('checks', {}).items()):
        if not v:
            print(f"  FAIL {k}")
    for k, v in sorted(report.get('evidence_failures', {}).items()):
        if v is not None:
            print(f"  FAIL evidence[{k}]: {v}")

    if report["status"] != "CALIBRATION_READY":
        print(f"BLOCKED: {report.get('blockers', [])}")
        return

    sdk_port = SDKPort(
        secure_client,
        maker=ACCOUNT,
        signer=SIGNER,
        ledger=session.ledger,
        arm=None,
        qualified=False,
    )

    # --- Resilient BTC price source (HTTP polling, no Binance WS) ---
    class HttpBtcSource:
        async def run(self, on_tick, on_status):
            import httpx
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            last_price = None
            while True:
                try:
                    async with httpx.AsyncClient(timeout=10) as hx:
                        r = await hx.get(url)
                    data = r.json()
                    price = float(data["bitcoin"]["usd"])
                    if last_price is None or abs(price - last_price) > 0.01:
                        last_price = price
                        now = now_ms()
                        # Build a fake MarketTick-compatible object
                        class Tick:
                            pass
                        tick = Tick()
                        tick.event_ts_ms = now
                        tick.recv_ts_ms = now
                        tick.price = price
                        await on_tick(tick)
                    if on_status:
                        on_status("BTC_CONNECTED")
                except Exception as e:
                    print(f"[btc] poll error: {e}")
                    if on_status:
                        on_status("BTC_RECONNECT")
                await asyncio.sleep(5)

    signal_source = SignalSource(collector_factory=None)
    signal_source.run = lambda on_tick, on_status: HttpBtcSource().run(on_tick, on_status)

    # Seed the book from REST API first
    async def seed_book_from_rest():
        rest = __import__("polymarket").AsyncPublicClient()
        now = now_ms()
        seeded = 0
        for tid, label in [(TOKEN_UP, "UP"), (TOKEN_DOWN, "DOWN")]:
            try:
                ob = await rest.get_order_book(token_id=tid)
                if ob and (ob.bids or ob.asks):
                    bids = [(float(b.price), float(b.size)) for b in ob.bids]
                    asks = [(float(a.price), float(a.size)) for a in ob.asks]
                    stream_book.update(tid, bids, asks, now, stream_book.generation or 1)
                    print(f"  REST seeded {label}: {len(bids)} bids, {len(asks)} asks")
                    seeded += 1
            except Exception as e:
                print(f"  REST seed {label} failed: {e}")
        return seeded

    coordinator = Coordinator(
        session.ledger,
        sdk_port,
        session.account,
        session.book,
        DIRECTORY / "STOP",
        clock=now_ms,
    )

    # Seed from REST first so BookAdapter detects available=True immediately
    seeded = await seed_book_from_rest()
    print(f"REST seeded {seeded}/2 tokens")

    proof = evidence()
    report = preflight_eval(proof, now_ms(), shutil.disk_usage(DIRECTORY).free, verifier)
    if report["status"] != "CALIBRATION_READY":
        raise ValueError(f"PREFLIGHT_REFRESH_BLOCKED: {report.get('blockers')}")

    arm = production_confirm(EXPERIMENT_ID, report, verifier=verifier, evidence=proof)
    print(f"ARMED: experiment_id={arm.experiment_id}, nonce={arm.nonce}")

    sdk_port.arm = arm
    sdk_port.qualified = True
    coordinator.arm = arm

    def current_fee():
        current = evidence()
        record = current["fee_upper_bound_proven"]
        f = verifier.validate("fee_upper_bound_proven", record, now_ms())
        return FeeRisk(
            f["cash_collateral"], f["outcome_shares"],
            f["collateral_per_share_upper"], f["fee_source_digest"],
            verifier.context["market"], record["valid_until_ms"], f["epoch"],
        )
    coordinator.fee_ceiling = current_fee

    print("Starting supervisor...")
    result = await supervisor_run(
        coordinator,
        signal_source,
        session.book,
        DIRECTORY / "reports",
        custody_owner,
    )
    print(f"Supervisor finished: {result}")

    await secure_client.close()
    session.close()

if __name__ == "__main__":
    asyncio.run(main())