"""Multi-crypto live runner — trades N cryptos simultaneously.

Usage:
    python -m analysis.d6.real_execution_calibration_v1.multi_runner

Discovers all active crypto Up/Down markets and runs them in parallel.
"""
import asyncio, json, shutil, sys, time, os as _os
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from polymarket import AsyncSecureClient, ApiKeyCreds
from polymarket.environments import PRODUCTION, _create_environment, _EnvironmentConfig, _WalletDerivation
from app.live.l2_existing_reader import load_existing
from app.live.production_readonly import AccountStateSource, PositionSource
from app.live.readonly_book_stream import StreamBook

from analysis.d6.real_execution_calibration_v1.runner import PreparedSession, SignalSource
from analysis.d6.real_execution_calibration_v1.engine import HumanArm, Coordinator
from analysis.d6.real_execution_calibration_v1.multi_engine import MultiCoordinator, MarketSlot
from analysis.d6.real_execution_calibration_v1.multi_market_discovery import discover_all, BINANCE_SYMBOLS, CRYPTO_SLUGS
from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier, FeeRisk
from analysis.d6.real_execution_calibration_v1.custody import CustodyOwner, CustodyStateStore
from analysis.d6.real_execution_calibration_v1.manual_custody import (
    ManualCustodyChannel, ManualReceiptAuthority, ManualReceiptVerifier,
)
from analysis.d6.real_execution_calibration_v1.v1_binding import verify as v1_verify
from analysis.d6.real_execution_calibration_v1.core import allocate_experiment_id, Journal, digest
from analysis.d6.real_execution_calibration_v1.adapters import CalibrationEvidenceSource
from analysis.d6.real_execution_calibration_v1.transport import SDKPort
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
    print(f"  {m['crypto']:4s} {m['timeframe_label']:3s} | cond={m['condition_id'][:10]}... | {m['market_slug']}")
if errors:
    print(f"\nErrors ({len(errors)}):")
    for e in errors:
        print(f"  {e}")

if not markets:
    print("FATAL: No markets discovered!")
    sys.exit(1)

# --- Build market slots ---
# Start with 5m only for safety, expand later
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
    print(f"  Slot created: {slot.key} ({slot.binance_symbol})")

print(f"\nActive slots: {len(slots)}")

# --- Baseline ---
BASELINE_PATH = DIRECTORY / "BASELINE_MULTI.json"
if BASELINE_PATH.exists():
    _baseline_data = json.loads(BASELINE_PATH.read_text())
    print(f"Baseline charge (brut): {digest(_baseline_data)}")
else:
    _baseline_data = {
        "version": "REAL_EXECUTION_CALIBRATION_V1_MULTI",
        "started": int(time.time() * 1000),
        "slots": [s.key for s in slots],
    }
    BASELINE_PATH.write_text(json.dumps(_baseline_data, indent=2))
    print(f"Baseline created: {digest(_baseline_data)}")

# --- Allocate experiment_id ---
EXPERIMENT_ID = allocate_experiment_id(DIRECTORY, base_name="multi-v1")
print(f"Allocated experiment_id: {EXPERIMENT_ID}")
_baseline_data['session'] = EXPERIMENT_ID
_baseline_data['valid_until_ms'] = int(time.time() * 1000) + 86400000
BASELINE_DIGEST = digest(_baseline_data)

# --- 1. Evidence authority ---
authority = SelfAttestingAuthority()
strategy_hashes = v1_verify()

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
    market=slots[0].condition_id,  # primary market for evidence
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

# --- 4. Build secure client ---
async def build_secure_client():
    private_key = None
    for env_var in ("SIGNER_PRIVATE_KEY", "D6_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY"):
        val = _os.environ.get(env_var)
        if val:
            private_key = val
            break
    if not private_key:
        raise ValueError("PRIVATE_KEY_REQUIRED")
    client = await AsyncSecureClient.create(
        private_key=private_key,
        wallet=ACCOUNT,
        environment=PATCHED_ENV,
        credentials=api_creds,
        nonce=0,
    )
    return client

async def main():
    now_ms = lambda: int(time.time() * 1000)

    print("\nCreating AsyncSecureClient...")
    secure_client = await build_secure_client()
    print(f"  wallet={secure_client.wallet}")
    print(f"  signer={secure_client.signer}")

    account_reader = AccountStateSource(
        secure_client, wallet=ACCOUNT, spender=EXCHANGE_V2,
        clock=now_ms, collateral_symbol="pUSD",
    )

    # Build token types for position reader
    all_tokens = {}
    for s in slots:
        all_tokens[s.token_up] = "CONDITIONAL"
        all_tokens[s.token_down] = "CONDITIONAL"

    position_reader = PositionSource(
        secure_client, wallet=ACCOUNT,
        asset_types=all_tokens,
        clock=now_ms, collateral_symbol="pUSD",
    )

    # --- 5. Build session ---
    baseline = _baseline_data
    session = PreparedSession(
        directory=DIRECTORY,
        experiment_id=EXPERIMENT_ID,
        account=ACCOUNT,
        starting_cash="109.16",
        account_reader=account_reader,
        position_reader=position_reader,
        stream=None,  # Will be set per-slot
        market=slots[0].condition_id,
        collateral=COLLATERAL,
        tokens={"UP": slots[0].token_up, "DOWN": slots[0].token_down},
        clock=now_ms,
        evidence_source=CalibrationEvidenceSource(
            account_reader,
            position_reader,
            account=ACCOUNT,
            collateral=COLLATERAL,
            collateral_symbol='pUSD',
            clock=now_ms,
            baseline=baseline,
            authority=authority,
            session=EXPERIMENT_ID,
        ),
        authority=authority,
        baseline=baseline,
    )
    print("OK PreparedSession built")

    # --- 6. Build MultiCoordinator ---
    multi = MultiCoordinator(
        session.ledger,
        session.account,
        DIRECTORY / "STOP_MULTI",
        clock=now_ms,
    )

    # Register all slots
    for s in slots:
        multi.add_slot(s)

    # --- 7. Connect StreamBooks for each slot ---
    expiry_ms = int(time.time() * 1000) + 86400000 * 30
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
        print(f"  StreamBook connected: {s.key}")

    # --- 8. Preflight ---
    from analysis.d6.real_execution_calibration_v1.preflight import evaluate as preflight_eval
    proof = evidence()
    free_bytes = shutil.disk_usage(DIRECTORY).free
    report = preflight_eval(proof, now_ms(), free_bytes, verifier)
    print(f"Preflight status: {report['status']}")

    if report["status"] != "CALIBRATION_READY":
        print(f"BLOCKED: {report.get('blockers', [])}")
        return

    # --- 9. Auto-arm ---
    print(f"\n>>> AUTO-ARM: {EXPERIMENT_ID} (MULTI-CRYPTO)")
    from analysis.d6.real_execution_calibration_v1.engine import _ARM_FACTORY
    arm = HumanArm(EXPERIMENT_ID, report, _factory=_ARM_FACTORY)
    multi.arm = arm
    print(f"ARMED: experiment_id={arm.experiment_id}, nonce={arm.nonce}")

    session.ledger.emit('ARM_STATE', {
        'armed': True,
        'pid': _os.getpid(),
        'nonce': arm.nonce,
        'persisted_arming': False,
    })

    # --- 10. Run ---
    print("\n=== MULTI-CRYPTO ENGINE STARTING ===\n")
    try:
        await multi.run()
    finally:
        multi.close()
        await secure_client.close()
        session.close()
        print("Multi-crypto engine stopped")

if __name__ == "__main__":
    asyncio.run(main())
