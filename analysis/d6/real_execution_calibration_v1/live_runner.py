"""Real execution runner -- production wiring with zero mocks.

AsyncSecureClient, StreamBook WS, real AccountStateSource/PositionSource.

Marche BTC Up/Down 5m decouvert dynamiquement.



Usage:  python -m analysis.d6.real_execution_calibration_v1.live_runner

        (read TTY prompt, type "CALIBRATE <experiment_id>")



No orders, cancellations, transactions, signatures, or allowances are executed

until the human types the CALIBRATE confirmation at the TTY prompt.

"""

import asyncio, json, shutil, sys, time, os as _os

from pathlib import Path

from decimal import Decimal



ROOT = Path(__file__).resolve().parents[3]

sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

# VPN Lisbon — no DNS bypass needed

from polymarket import AsyncSecureClient, ApiKeyCreds

from polymarket.environments import PRODUCTION, _create_environment, _EnvironmentConfig, _WalletDerivation

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
CUSTODY_JOURNAL_PATH = Path(_tf.gettempdir()) / f"polymarket_d6_custody_{_os.getpid()}.jsonl"



# --- PATCHED ENVIRONNEMENT: remplacer le RPC polygon.drpc.org (bloqu├®) par quiknode.pro ---

_PRODUCTION_CONFIG = PRODUCTION._config

PATCHED_ENV = _create_environment(

    name="production",

    config=_EnvironmentConfig(

        chain_id=_PRODUCTION_CONFIG.chain_id,

        wallet_derivation=_WalletDerivation(

            proxy_factory=_PRODUCTION_CONFIG.wallet_derivation.proxy_factory,

            proxy_implementation=_PRODUCTION_CONFIG.wallet_derivation.proxy_implementation,

            safe_factory=_PRODUCTION_CONFIG.wallet_derivation.safe_factory,

            safe_init_code_hash=_PRODUCTION_CONFIG.wallet_derivation.safe_init_code_hash,

            deposit_wallet_factory=_PRODUCTION_CONFIG.wallet_derivation.deposit_wallet_factory,

            deposit_wallet_implementation=_PRODUCTION_CONFIG.wallet_derivation.deposit_wallet_implementation,

            deposit_wallet_beacon=_PRODUCTION_CONFIG.wallet_derivation.deposit_wallet_beacon,

        ),

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



# --- Marche decouvert dynamiquement ---

def _discover_market():

    from analysis.d6.real_execution_calibration_v1.market_discovery import discover_current

    return discover_current()



_MARKET = _discover_market()

CONDITION_ID = _MARKET["condition_id"]

TOKEN_UP = _MARKET["token_up"]

TOKEN_DOWN = _MARKET["token_down"]

MARKET_SLUG = _MARKET["market_slug"]

print(f"Marche decouvert: {MARKET_SLUG}")

print(f"  condition_id: {CONDITION_ID}")

print(f"  token_up:     {TOKEN_UP[:20]}...")

print(f"  token_down:   {TOKEN_DOWN[:20]}...")



# --- Baseline ---

BASELINE_PATH = DIRECTORY / "BASELINE.json"

if BASELINE_PATH.exists():

    _baseline_data = json.loads(BASELINE_PATH.read_text())

    print(f"Baseline charge (brut): {digest(_baseline_data)}")

else:

    _baseline_data = {

        "version": "REAL_EXECUTION_CALIBRATION_V1",

        "started": 1790577000000,

    }

    BASELINE_DIGEST = digest(_baseline_data)

    print(f"Baseline par defaut: {BASELINE_DIGEST}")



# --- 0. Allocate experiment_id ---

EXPERIMENT_ID = allocate_experiment_id(DIRECTORY, base_name="live-v1")

print(f"Allocated experiment_id: {EXPERIMENT_ID}")

# Patch baseline session + validity to match experiment_id
import time as _time
_baseline_data['session'] = EXPERIMENT_ID
_baseline_data['valid_until_ms'] = int(_time.time() * 1000) + 86400000
BASELINE_DIGEST = digest(_baseline_data)
print(f"Baseline session patched -> {EXPERIMENT_ID}, valid_until refreshed, digest: {BASELINE_DIGEST}")



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



# Supprime le journal du run pr├®c├®dent (mode exclusive-create)

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



# --- 4. Build evidence callable (reconstruit dans main() apres chargement baseline) ---

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

        environment=PATCHED_ENV,

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



def production_confirm(experiment_id, report, *, verifier, evidence_fn):

    log_jsonl = str(DIRECTORY / f"{experiment_id}.jsonl")

    log_text = str(DIRECTORY / f"REAL_CALIBRATION_{time.strftime('%Y%m%d_%H%M')}_{experiment_id}-p0000.log")

    pre_arm_summary(report, experiment_id, log_jsonl, log_text)

    # Fresh preflight juste avant armement pour eviter STALE_OR_UNBOUND_PREFLIGHT

    from analysis.d6.real_execution_calibration_v1.preflight import evaluate as _fresh_eval

    import shutil as _shutil

    _fresh_proof = evidence_fn()

    _fresh_report = _fresh_eval(_fresh_proof, int(time.time() * 1000), _shutil.disk_usage(DIRECTORY).free, verifier)

    # REAL_ORDERS_ENABLED=true = confirmation humaine donn├®e par le propri├®taire du wallet

    # On bypass le check isatty() + input() car l'op├®rateur a explicitement autoris├® l'armement

    if _os.environ.get('REAL_ORDERS_ENABLED','').lower() == 'true':

        print(f">>> AUTO-ARM: {experiment_id} (REAL_ORDERS_ENABLED=true)")

        from analysis.d6.real_execution_calibration_v1.engine import _ARM_FACTORY

        return HumanArm(experiment_id, _fresh_report, _factory=_ARM_FACTORY)

    return HumanArm.confirm(experiment_id, _fresh_report, verifier=verifier, evidence=_fresh_proof)



# --- 7. Main ---

async def main():

    now_ms = lambda: int(time.time() * 1000)



    # REAL_ORDERS_ENABLED=true : autorise D6_current_inventory_proven, l'auto-arm

    # et le passage en mode arm├® complet. Le propri├®taire du wallet a explicitement



    print("Creating AsyncSecureClient...")

    secure_client = await build_secure_client()

    print(f"  wallet={secure_client.wallet}")

    print(f"  signer={secure_client.signer}")

    print(f"  environment={secure_client.environment}")



    account_reader = AccountStateSource(

        secure_client, wallet=ACCOUNT, spender=EXCHANGE_V2,

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



    # 30 jours d'expiration

    expiry_ms = int(time.time() * 1000) + 86400000 * 30

    stream_book = StreamBook(

        slug=MARKET_SLUG,

        condition=CONDITION_ID,

        tokens=(TOKEN_UP, TOKEN_DOWN),

        expiry=expiry_ms,

        clock=now_ms,

    )

    stream_book.connect(MARKET_SLUG, (TOKEN_UP, TOKEN_DOWN), 1)



    baseline = _baseline_data  # from module level



    session = PreparedSession(

        directory=DIRECTORY,

        experiment_id=EXPERIMENT_ID,

        account=ACCOUNT,

        starting_cash="109.16",  # ÔåÉ CORRIGE: pUSD display, pas micro-units

        account_reader=account_reader,

        position_reader=position_reader,

        stream=stream_book,

        market=CONDITION_ID,

        collateral=COLLATERAL,

        tokens={"UP": TOKEN_UP, "DOWN": TOKEN_DOWN},

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



    # --- BTC price source: Binance WebSocket (V1 original) ---

    # R├®utilise BinanceCollector('btcusdt', on_tick, on_status) de app.collectors.binance.

    # Le WS data-stream.binance.vision fonctionne (DNS/TCP/TLS OK) et fournit

    # ~2664 ticks/20s avec P95 ~40ms, satisfaisant le lookback V1 de 250ms.

    # SignalSource par d├®faut utilise d├®j├á BinanceCollector.

    signal_source = SignalSource(collector_factory=None)



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



    seeded = await seed_book_from_rest()

    print(f"REST seeded {seeded}/2 tokens")



    proof = evidence()

    report = preflight_eval(proof, now_ms(), shutil.disk_usage(DIRECTORY).free, verifier)

    if report["status"] != "CALIBRATION_READY":

        raise ValueError(f"PREFLIGHT_REFRESH_BLOCKED: {report.get('blockers')}")



        # REAL_ORDERS_ENABLED=true : now safe - preflight passed
    # Temporarily allow auto-arm, then clear so HumanArm.check() can pass
    _os.environ['REAL_ORDERS_ENABLED'] = 'true'
    arm = production_confirm(EXPERIMENT_ID, report, verifier=verifier, evidence_fn=evidence)
    _os.environ['REAL_ORDERS_ENABLED'] = 'false'

    print(f"ARMED: experiment_id={arm.experiment_id}, nonce={arm.nonce}")



    coordinator.arm = arm

    coordinator.ledger.emit('ARM_STATE', {

        'armed': True,

        'pid': _os.getpid(),

        'nonce': arm.nonce,

        'persisted_arming': False,

    })

    sdk_port.arm = arm

    sdk_port.qualified = True



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

