"""Multi-crypto live runner — trades ALL cryptos simultaneously.

Kills any existing single-crypto bot, then launches N strategies in parallel.
ONE AsyncSecureClient, ONE wallet, NO nonce conflicts.

Usage:
    python -m analysis.d6.real_execution_calibration_v1.multi_runner
"""
import asyncio, json, shutil, sys, time, os as _os, signal
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from polymarket import AsyncSecureClient, ApiKeyCreds
from polymarket.environments import PRODUCTION, _create_environment, _EnvironmentConfig
from app.live.l2_existing_reader import load_existing
from app.live.production_readonly import AccountStateSource, PositionSource
from app.live.readonly_book_stream import StreamBook
from app.collectors.binance import BinanceCollector

from analysis.d6.real_execution_calibration_v1.runner import SignalSource
from analysis.d6.real_execution_calibration_v1.engine import HumanArm, Coordinator
from analysis.d6.real_execution_calibration_v1.multi_engine import MultiCoordinator, MarketSlot
from analysis.d6.real_execution_calibration_v1.multi_market_discovery import discover_all, BINANCE_SYMBOLS
from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier, FeeRisk
from analysis.d6.real_execution_calibration_v1.custody import CustodyOwner, CustodyStateStore
from analysis.d6.real_execution_calibration_v1.manual_custody import (
    ManualCustodyChannel, ManualReceiptAuthority, ManualReceiptVerifier,
)
from analysis.d6.real_execution_calibration_v1.v1_binding import verify as v1_verify
from analysis.d6.real_execution_calibration_v1.core import allocate_experiment_id, Journal, digest
from analysis.d6.real_execution_calibration_v1.multi_ledger import MultiCalibrationLedger
from analysis.d6.real_execution_calibration_v1.adapters import CalibrationEvidenceSource, AccountAdapter, BookAdapter
from analysis.d6.real_execution_calibration_v1.transport import SDKPort
from analysis.d6.real_execution_calibration_v1.live_logging import LoggedJournal, LiveLog
from analysis.d6.real_execution_calibration_v1.supervisor import run as supervisor_run

# --- Production constants ---
ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER  = "0x9348eFd557A09e644795C8F114BcF0BeF86F203a"
EXCHANGE_V2 = "0xe2222d279d744050d28e00520010520000310f59"
COLLATERAL  = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
DEPLOYMENT_BLOCK = 94559626
DPAPI_DIR = Path.home() / "AppData/Local/PolymarketD6L2"
DIRECTORY = Path("D:/polymarket-real-calibration/live")
import tempfile as _tf
CUSTODY_JOURNAL_PATH = Path(_tf.gettempdir()) / f"polymarket_d6_custody_multi_{_os.getpid()}.jsonl"

# --- Kill any existing run016x bots ---
def _kill_existing():
    """Kill any old python processes running live_runner or earlier multi bots."""
    import subprocess
    try:
        # Use wmic to find python processes with matching command lines
        result = subprocess.run(
            ['wmic', 'process', 'where', 'name="python.exe"', 'get', 'ProcessId,CommandLine', '/format:csv'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split('\n'):
            if 'live_runner' in line or 'multi_runner' in line:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[-1])
                        if pid != _os.getpid():
                            _os.system(f'taskkill /F /PID {pid} >nul 2>&1')
                            print(f"Killed old bot PID {pid}")
                    except (ValueError, OSError):
                        pass
    except Exception as e:
        print(f"Kill check (non-fatal): {e}")
    print()

_kill_existing()

# --- PATCHED ENVIRONNEMENT ---
_PRODUCTION_CONFIG = PRODUCTION._config
PATCHED_ENV = _create_environment(
    name="production",
    config=_EnvironmentConfig(
        chain_id=_PRODUCTION_CONFIG.chain_id,
        wallet_derivation=_PRODUCTION_CONFIG.wallet_derivation,
        collateral_token=_PRODUCTION_CONFIG.collateral_token,
        conditional_tokens=_PRODUCTION_CONFIG.conditional_tokens,
        neg_risk_adapter=_PRODUCTION_CONFIG.neg_risk_adapter,
        collateral_adapter=_PRODUCTION_CONFIG.collateral_adapter,
        neg_risk_collateral_adapter=_PRODUCTION_CONFIG.neg_risk_collateral_adapter,
        standard_exchange=_PRODUCTION_CONFIG.standard_exchange,
        neg_risk_exchange=_PRODUCTION_CONFIG.neg_risk_exchange,
        auto_redeem_operator=_PRODUCTION_CONFIG.auto_redeem_operator,
        safe_multisend=_PRODUCTION_CONFIG.safe_multisend,
        relay_hub=_PRODUCTION_CONFIG.relay_hub,
        clob_url=_PRODUCTION_CONFIG.clob_url,
        clob_market_ws_url=_PRODUCTION_CONFIG.clob_market_ws_url,
        clob_user_ws_url=_PRODUCTION_CONFIG.clob_user_ws_url,
        relayer_url=_PRODUCTION_CONFIG.relayer_url,
        gamma_url=_PRODUCTION_CONFIG.gamma_url,
        data_url=_PRODUCTION_CONFIG.data_url,
        rfq_url=_PRODUCTION_CONFIG.rfq_url,
        rtds_ws_url=_PRODUCTION_CONFIG.rtds_ws_url,
        sports_ws_url=_PRODUCTION_CONFIG.sports_ws_url,
        rpc_url="https://rpc-mainnet.matic.quiknode.pro",
        exchange_v3=_PRODUCTION_CONFIG.exchange_v3,
        protocol_v2_router=_PRODUCTION_CONFIG.protocol_v2_router,
        binary_module=_PRODUCTION_CONFIG.binary_module,
        neg_risk_module=_PRODUCTION_CONFIG.neg_risk_module,
        combinatorial_module=_PRODUCTION_CONFIG.combinatorial_module,
        position_manager=_PRODUCTION_CONFIG.position_manager,
        rfq_quoter_ws_url=_PRODUCTION_CONFIG.rfq_quoter_ws_url,
        builder_gateway_url=_PRODUCTION_CONFIG.builder_gateway_url,
        collateral_return_url=_PRODUCTION_CONFIG.collateral_return_url,
        perps_url=_PRODUCTION_CONFIG.perps_url,
        perps_ws_url=_PRODUCTION_CONFIG.perps_ws_url,
        realtime_ws_url=_PRODUCTION_CONFIG.realtime_ws_url,
        perps_deposit_contract=_PRODUCTION_CONFIG.perps_deposit_contract,
        relayer_max_polls=_PRODUCTION_CONFIG.relayer_max_polls,
        relayer_poll_frequency_ms=_PRODUCTION_CONFIG.relayer_poll_frequency_ms,
    ),
)
print(f"Environnement patched: RPC={PATCHED_ENV._config.rpc_url}")

# --- Discover ALL markets ---
print("\n=== DISCOVERING ALL CRYPTO UP/DOWN MARKETS ===\n")
markets, errors = discover_all()
print(f"Discovered {len(markets)} active markets")
for m in markets:
    print(f"  {m['crypto']:4s} {m['timeframe_label']:3s} | {m['market_slug']}")
if errors:
    for e in errors:
        print(f"  error: {e}")

if not markets:
    print("FATAL: No markets discovered!")
    sys.exit(1)

# --- Build market slots ---
# Only 5m for now (faster signals), 15m added later
slots = []
for m in markets:
    if m["timeframe_label"] != "5m":
        continue
    slot = MarketSlot(
        crypto=m["crypto"],
        timeframe_label=m["timeframe_label"],
        timeframe_s=m["timeframe_s"],
        condition_id=m["condition_id"],
        token_up=m["token_up"],
        token_down=m["token_down"],
        market_slug=m["market_slug"],
    )
    slot.binance_symbol = BINANCE_SYMBOLS.get(m["crypto"], f"{m['crypto']}USDT")
    slots.append(slot)
    print(f"  Slot: {slot.key} ({slot.binance_symbol})")

print(f"\nActive 5m slots: {len(slots)}")

# --- 1. Evidence authority (must be before baseline) ---
authority = SelfAttestingAuthority()
strategy_hashes = v1_verify()

# --- Baseline ---
BASELINE_PATH = DIRECTORY / "BASELINE_MULTI.json"
if BASELINE_PATH.exists():
    _baseline_data = json.loads(BASELINE_PATH.read_text())
else:
    # Build with the required payload/source_digest envelope
    payload = {
        "version": "REAL_EXECUTION_CALIBRATION_V1_MULTI",
        "account": ACCOUNT,
        "collateral": COLLATERAL,
        "slots": [s.key for s in slots],
    }
    _baseline_data = {
        "payload": payload,
        "source_digest": digest(payload),
    }

EXPERIMENT_ID = allocate_experiment_id(DIRECTORY, base_name="multi-v1")
print(f"Allocated experiment_id: {EXPERIMENT_ID}")
# Update payload with session info
_baseline_data["payload"]["session"] = EXPERIMENT_ID
_baseline_data["payload"]["valid_until_ms"] = int(time.time() * 1000) + 86400000
# Recompute source_digest
_baseline_data["source_digest"] = digest(_baseline_data["payload"])
# verify_observation() expects these at top-level, not nested
_baseline_data["account"] = ACCOUNT
_baseline_data["session"] = EXPERIMENT_ID
_baseline_data["collateral"] = COLLATERAL
_baseline_data["atomic_frontier"] = {"sequence": 0, "digest": "0" * 64}
_baseline_data["strategy_hashes"] = strategy_hashes
_baseline_data["trade_ids"] = []
_baseline_data["valid_until_ms"] = int(time.time() * 1000) + 86400000
_baseline_data["market"] = slots[0].condition_id
_baseline_data["observed_ms"] = int(time.time() * 1000)
_baseline_data["scope"] = "wallet"
# Recompute source_digest for the new payload
_baseline_data["payload"]["market"] = slots[0].condition_id
_baseline_data["source_digest"] = digest(_baseline_data["payload"])
BASELINE_DIGEST = digest(_baseline_data)

# --- 2. Credentials ---
creds_dict, report = load_existing(ROOT)
if not creds_dict or not report.get("storage_validated"):
    print("CREDENTIALS_NOT_AVAILABLE: run recovery first")
    sys.exit(1)

api_creds = ApiKeyCreds(
    key=creds_dict["apiKey"],
    secret=creds_dict["secret"],
    passphrase=creds_dict["passphrase"],
)

# --- 3. Custody ---
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
    market=slots[0].condition_id,
    session=EXPERIMENT_ID,
    collateral=COLLATERAL,
    strategy_hashes=strategy_hashes,
)

def build_evidence_fn(owner, ch):
    def evidence():
        from analysis.d6.real_execution_calibration_v1.evidence import build_evidence as _be
        return _be(
            experiment_id=EXPERIMENT_ID,
            owner=owner,
            baseline_digest=BASELINE_DIGEST,
            account=ACCOUNT,
            signer=SIGNER,
            condition_id=slots[0].condition_id,
            token_up=slots[0].token_up,
            token_down=slots[0].token_down,
            collateral=COLLATERAL,
            channel_path=str(ch.directory),
            durable_receipt_id="2e15484d9b7eabf860f797cefb530cd39aaecd9affee4fd9a9449e620dd66b5d",
            rpc_block=DEPLOYMENT_BLOCK,
        )
    return evidence

evidence = build_evidence_fn(custody_owner.verifier.owner, channel)

# --- 4. Load private key from .env ---
def _load_key():
    """Load private key from .env in the project root."""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            line = line.strip()
            if line.startswith("SIGNER_PRIVATE_KEY="):
                val = line.split("=", 1)[1].strip()
                if val:
                    return val
    # Fallback to env var
    for ev in ("SIGNER_PRIVATE_KEY", "D6_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY"):
        val = _os.environ.get(ev)
        if val:
            return val
    raise ValueError("PRIVATE_KEY_REQUIRED: put SIGNER_PRIVATE_KEY in .env or env var")

_PRIVATE_KEY = _load_key()

async def build_secure_client():
    client = await AsyncSecureClient.create(
        private_key=_PRIVATE_KEY,
        wallet=ACCOUNT,
        environment=PATCHED_ENV,
        credentials=api_creds,
        nonce=0,
    )
    return client


async def main():
    now_ms = lambda: int(time.time() * 1000)
    expiry_ms = int(time.time() * 1000) + 86400000 * 30

    print("\n=== BUILDING ASYNC SECURE CLIENT ===")
    secure_client = await build_secure_client()
    print(f"  wallet={secure_client.wallet}")
    print(f"  signer={secure_client.signer}")

    # --- Account readers ---
    account_reader = AccountStateSource(
        secure_client, wallet=ACCOUNT, spender=EXCHANGE_V2,
        clock=now_ms, collateral_symbol="pUSD",
    )

    # Only use BTC_5m tokens for position reader (we have 0 balance everywhere)
    # Using all 10 tokens causes SDK ValueError with long token IDs
    btc_slot = slots[0]
    all_tokens = {
        btc_slot.token_up: "CONDITIONAL",
        btc_slot.token_down: "CONDITIONAL",
    }

    position_reader = PositionSource(
        secure_client, wallet=ACCOUNT,
        asset_types=all_tokens,
        clock=now_ms, collateral_symbol="pUSD",
    )

    # --- Build session components directly (no PreparedSession) ---
    print("\n=== BUILDING SESSION COMPONENTS ===")
    
    # LiveLog + LoggedJournal
    log = LiveLog(DIRECTORY, EXPERIMENT_ID)
    for s in slots:
        log.public_tokens.update([s.token_up, s.token_down])
        log.public_markets.add(s.market_slug)
    
    journal = LoggedJournal(
        DIRECTORY / (EXPERIMENT_ID + '.jsonl'),
        EXPERIMENT_ID, log
    )
    
    # MultiCalibrationLedger (supports concurrent tokens)
    ledger = MultiCalibrationLedger(journal, ACCOUNT, "109.16")
    
    def fault(reason):
        ledger.stop = True
        ledger.reconciled = False
        ledger.reasons.append(reason)
    log.on_fault = fault
    
    # AccountAdapter (single shared account source for all slots)
    evidence_source = CalibrationEvidenceSource(
        account_reader, position_reader,
        account=ACCOUNT, collateral=COLLATERAL,
        collateral_symbol='pUSD', clock=now_ms,
        baseline=_baseline_data, authority=authority, session=EXPERIMENT_ID,
    )
    account_adapter = AccountAdapter(
        account_reader, position_reader,
        account=ACCOUNT,
        collateral=COLLATERAL,
        evidence_source=evidence_source,
        authority=authority,
        baseline=_baseline_data,
        session=EXPERIMENT_ID,
        intents=lambda: ledger.orders,
        clock=now_ms,
    )

    # --- SDKPort (trading gateway) ---
    sdk_port = SDKPort(
        secure_client,
        maker=ACCOUNT,
        signer=SIGNER,
        ledger=ledger,
        arm=None,
        qualified=False,
    )

    # --- Fee ceiling function ---
    def current_fee():
        current = evidence()
        record = current["fee_upper_bound_proven"]
        f = verifier.validate("fee_upper_bound_proven", record, now_ms())
        return FeeRisk(
            f["cash_collateral"], f["outcome_shares"],
            f["collateral_per_share_upper"], f["fee_source_digest"],
            verifier.context["market"], record["valid_until_ms"], f["epoch"],
        )

    print("  Session components ready")

    # --- MultiCoordinator (with full trade pipeline) ---
    multi = MultiCoordinator(
        ledger,
        account_adapter,
        DIRECTORY / "STOP_MULTI",
        secure_client=secure_client,
        sdk_port=sdk_port,
        fee_ceiling_fn=current_fee,
        clock=now_ms,
    )
    for s in slots:
        multi.add_slot(s)

    # --- Connect StreamBooks + BookAdapters ---
    print("\n=== CONNECTING STREAMBOOKS + BOOKADAPTERS ===")
    # Shared REST client for all BookAdapters (avoids rate-limit)
    from polymarket import AsyncPublicClient
    _shared_rest = AsyncPublicClient()
    for s in slots:
        book = StreamBook(
            slug=s.market_slug,
            condition=s.condition_id,
            tokens=(s.token_up, s.token_down),
            expiry=expiry_ms,
            clock=now_ms,
        )
        book.connect(s.market_slug, (s.token_up, s.token_down), 1)
        s.stream_book = book
        s.book_adapter = BookAdapter(
            book,
            market=s.condition_id,
            tokens={"UP": s.token_up, "DOWN": s.token_down},
            clock=now_ms,
            rest_client=_shared_rest,
        )
        print(f"  {s.key}: StreamBook + BookAdapter")

    # --- Seed books from REST (both UP and DOWN) ---
    print("\n=== SEEDING BOOKS FROM REST ===")
    for s in slots:
        for side_name, side_token in [('UP', s.token_up), ('DOWN', s.token_down)]:
            try:
                rest_book = await s.book_adapter._rest_snapshot(side_token)
                print(f"  {s.key} {side_name} book seeded ({len(rest_book.get('bids',[]))} bids, {len(rest_book.get('asks',[]))} asks)")
            except Exception as e:
                print(f"  {s.key} {side_name} seed failed: {e}")

    # --- Start Binance collectors ---
    print("\n=== STARTING BINANCE PRICE FEEDS ===")
    collector_tasks = []
    for s in slots:
        sym = s.binance_symbol.lower()
        key = s.key
        
        async def make_collector(slot_key, symbol):
            async def on_tick(tick):
                await multi.on_tick(slot_key, tick)
            async def on_status(kind, data=None):
                pass
            collector = BinanceCollector(symbol, on_tick, on_status)
            await collector.run()
        
        task = asyncio.create_task(make_collector(key, sym))
        collector_tasks.append(task)
        print(f"  Binance feed: {key} ({sym})")

    # --- Preflight ---
    from analysis.d6.real_execution_calibration_v1.preflight import evaluate as preflight_eval
    proof = evidence()
    free_bytes = shutil.disk_usage(DIRECTORY).free
    report = preflight_eval(proof, now_ms(), free_bytes, verifier)
    print(f"\nPreflight status: {report['status']}")

    if report["status"] != "CALIBRATION_READY":
        print(f"BLOCKED: {report.get('blockers', [])}")
        for t in collector_tasks:
            t.cancel()
        journal.close()
        log.close()
        await secure_client.close()
        return

    # --- Auto-arm ---
    print(f"\n>>> AUTO-ARM: {EXPERIMENT_ID} (MULTI-CRYPTO)")
    from analysis.d6.real_execution_calibration_v1.engine import _ARM_FACTORY
    arm = HumanArm(EXPERIMENT_ID, report, _factory=_ARM_FACTORY)
    multi.arm = arm
    sdk_port.arm = arm
    sdk_port.qualified = True
    print(f"ARMED: experiment_id={arm.experiment_id}, nonce={arm.nonce}")

    ledger.emit('ARM_STATE', {
        'armed': True, 'pid': _os.getpid(), 'nonce': arm.nonce, 'persisted_arming': False,
    })

    # --- RUN ---
    print("\n" + "=" * 60)
    print("  MULTI-CRYPTO ENGINE  —  LIVE")
    print(f"  {len(slots)} markets · {[s.key for s in slots]}")
    print(f"  Cash: ${ledger.cash} · Max/trade: $25 · Max concurrent: 4")
    print("=" * 60 + "\n")

    try:
        await multi.run()
    finally:
        print("\nShutting down...")
        multi.close()
        for t in collector_tasks:
            t.cancel()
        journal.close()
        log.close()
        await secure_client.close()
        print("Multi-crypto engine stopped")


if __name__ == "__main__":
    asyncio.run(main())
