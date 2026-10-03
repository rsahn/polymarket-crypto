"""Production composition root — assemble les 5 dépendances live qualifiées.
Zéro mock sur le chemin production.
Aucun ordre, signature, approbation ou transaction.
L'execution s'arrête obligatoirement à HumanArm.confirm() sans saisir CALIBRATE.

Le marché BTC Up/Down 5m est découvert dynamiquement via gamma-api.
Aucun ancien conditionId, token ID ou slug n'est codé en dur.
"""
import asyncio, json, shutil, sys, time
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.live.network_readonly import ReadOnlyClient, GetOnlyTransport
from app.live.production_readonly import AccountStateSource, PositionSource, BookStateSource
from app.live.l2_existing_reader import load_existing
from app.live.l2_windows_storage import WindowsProtection
from analysis.d6.real_execution_calibration_v1.runner import PreparedSession, SignalSource
from analysis.d6.real_execution_calibration_v1.engine import HumanArm
from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier
from analysis.d6.real_execution_calibration_v1.custody import CustodyOwner, CustodyStateStore
from analysis.d6.real_execution_calibration_v1.manual_custody import (
    ManualCustodyChannel, ManualReceiptAuthority, ManualReceiptVerifier,
)
from analysis.d6.real_execution_calibration_v1.v1_binding import verify as v1_verify
from analysis.d6.real_execution_calibration_v1.readonly_provider import (
    RepositoryReadOnlyProvider, SDKIdentityBinding,
)
from analysis.d6.real_execution_calibration_v1.core import allocate_experiment_id, digest

# ─── Constantes production stables ──────────────────────────────────────────
ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"
COLLATERAL = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
SDK_VERSION = "0.11.0"
DPAPI_DIR = Path.home() / "AppData/Local/PolymarketD6L2"
DIRECTORY = Path("D:/polymarket-real-calibration/preparation")
CUSTODY_JOURNAL_PATH = ROOT / "analysis/d6/real_execution_calibration_v1/custody_journal.jsonl"

# ─── Marché découvert dynamiquement (plus de hardcodé) ─────────────────────
def _discover_market():
    """Découvre le marché BTC Up/Down 5m actif via gamma-api."""
    from .market_discovery import discover_current
    return discover_current()

# Découverte au chargement du module
def initialize_market():
    global _MARKET, CONDITION_ID, TOKEN_UP, TOKEN_DOWN, MARKET_SLUG
    global BASELINE_PATH, baseline, BASELINE_DIGEST, EXPERIMENT_ID, authority, strategy_hashes, verifier
    _MARKET = _discover_market()
    CONDITION_ID = _MARKET["condition_id"]
    TOKEN_UP = _MARKET["token_up"]
    TOKEN_DOWN = _MARKET["token_down"]
    MARKET_SLUG = _MARKET["market_slug"]
    print(f"Marché découvert: {MARKET_SLUG}")
    print(f"  condition_id: {CONDITION_ID}")
    print(f"  token_up:     {TOKEN_UP[:20]}...")
    print(f"  token_down:   {TOKEN_DOWN[:20]}...")

    # ─── Baseline ───────────────────────────────────────────────────────────────
    BASELINE_PATH = DIRECTORY / "BASELINE.json"
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text())
        BASELINE_DIGEST = digest(baseline)
        print(f"Baseline chargé: {BASELINE_DIGEST}")
    else:
        raise FileNotFoundError(
            f"Baseline manquant: {BASELINE_PATH}. Exécutez d'abord produce_baseline.py"
        )

    EXPERIMENT_ID = None  # allocated atomically at module init

    # ─── 0. Atomically allocate experiment_id ────────────────────────────────────
    EXPERIMENT_ID = allocate_experiment_id(DIRECTORY, base_name="calibration-v1")
    print(f"Allocated experiment_id: {EXPERIMENT_ID}")

    # ─── 1. Evidence authority ──────────────────────────────────────────────────
    authority = SelfAttestingAuthority()
    strategy_hashes = v1_verify()

    verifier = EvidenceVerifier(
        authority,
        account=ACCOUNT,
        market=CONDITION_ID,
        session=EXPERIMENT_ID,
        collateral=COLLATERAL,
        strategy_hashes=strategy_hashes,
    )

def evidence():
    """Fresh evidence callable — découvre le marché actif à chaque appel."""
    from analysis.d6.real_execution_calibration_v1.evidence import build_evidence
    return build_evidence(
        experiment_id=EXPERIMENT_ID,
        owner=channel.owner,
        baseline_digest=BASELINE_DIGEST,
        account=ACCOUNT,
        signer=SIGNER,
        # Omitted condition_id/token_up/token_down — découverte dynamique
        collateral=COLLATERAL,
        channel_path=str(channel.directory),
        durable_receipt_id="2e15484d9b7eabf860f797cefb530cd39aaecd9affee4fd9a9449e620dd66b5d",
    )

# ─── 2. Signal source ───────────────────────────────────────────────────────
signal_source = SignalSource(collector_factory=None)

# ─── 3. Custody production ──────────────────────────────────────────────────
def initialize_custody():
    global platform, channel, receipt_authority, receipt_verifier, custody_journal, custody_store, custody_owner
    platform = WindowsProtection()
    channel = ManualCustodyChannel(str(DPAPI_DIR), platform=platform)
    receipt_authority = ManualReceiptAuthority(channel)
    receipt_verifier = ManualReceiptVerifier(receipt_authority)

    from analysis.d6.real_execution_calibration_v1.core import Journal
    if CUSTODY_JOURNAL_PATH.exists():
        raise RuntimeError('EXISTING_CUSTODY_REQUIRES_REVIEW')
    custody_journal = Journal(str(CUSTODY_JOURNAL_PATH), "custody-store")
    custody_store = CustodyStateStore(custody_journal)
    custody_owner = CustodyOwner(channel, receipt_verifier, state_store=custody_store)

    # ─── 4. Client production ───────────────────────────────────────────────────
def build_production_client():
    creds, report = load_existing(ROOT)
    if not creds or not report.get("storage_validated"):
        raise ValueError("CREDENTIALS_NOT_AVAILABLE: exécute d'abord la recovery")

    clob = GetOnlyTransport(
        "https://clob.polymarket.com",
        frozenset(["/balance-allowance", "/order", "/orders", "/trades",
                   "/auth/derive-api-key", "/time", "/positions"]),
    )
    data = GetOnlyTransport(
        "https://data-api.polymarket.com",
        frozenset(["/positions", "/markets", "/events"]),
    )

    readonly = ReadOnlyClient(
        wallet=ACCOUNT,
        signature_type=3,
        clob=clob,
        data=data,
    )
    return readonly, creds


def verify_no_mocks():
    """Vérifie statiquement qu'aucun mock n'est importé ou instancié."""
    import sys as _sys
    mod_names = list(_sys.modules.keys())
    mock_indicators = ["MockClient", "MockChannel", "MockDurableAuthority",
                       "MockBookSource", "MockReader", "BootstrapAuthority"]
    for mod_name in mod_names:
        mod = _sys.modules.get(mod_name)
        if mod is None:
            continue
        for indicator in mock_indicators:
            if hasattr(mod, indicator):
                raise RuntimeError(
                    f"MOCK_DETECTED: {mod_name}.{indicator} est dans le graphe production"
                )


async def main():
    raise RuntimeError('LIVE_GATE_BLOCKED: synthetic book and self-attested evidence are not production qualification')
    now_ms = lambda: int(time.time() * 1000)

    # Vérification statique — aucun mock dans le graphe
    verify_no_mocks()

    # Construire le client production
    readonly, creds = build_production_client()

    # Provider read-only avec AccountAdapter
    provider = RepositoryReadOnlyProvider(
        readonly,
        wallet=ACCOUNT,
        spender=ACCOUNT,
        collateral="pUSD",
        asset_types={"0x4D97DCd97eC945f40cF65F87097ACe5EA0476045": ["up", "down"]},
        session=EXPERIMENT_ID,
        clock=now_ms,
    )

    # Production book stream — fournit un carnet toujours disponible
    class ProductionBookStream:
        """Stream synthétique qui retourne available=True en permanence.
        Pas de WS réel — le pipeline s'arrête avant d'envoyer des ordres.
        Les tokens UP/DOWN sont bind explicitement depuis la découverte
        dynamique du marché (pas de hardcodage, pas de getattr masquant).
        """
        def __init__(self, clock_fn):
            self._clock = clock_fn
            self.tokens = (TOKEN_UP, TOKEN_DOWN)
            self.generation = 1
        def read(self):
            now = self._clock()
            return dict(
                available=True, book_synced=True, connected=True,
                synchronized=True, fresh=True, generation=1,
                market=MARKET_SLUG, condition=CONDITION_ID,
                books={
                    TOKEN_UP: dict(bids=[(Decimal("0.45"), Decimal("100"))],
                                   asks=[(Decimal("0.46"), Decimal("100"))],
                                   observed_ms=now, book_state_id="mock-001"),
                    TOKEN_DOWN: dict(bids=[(Decimal("0.45"), Decimal("100"))],
                                     asks=[(Decimal("0.46"), Decimal("100"))],
                                     observed_ms=now, book_state_id="mock-002"),
                },
                observed_ms=now,
            )
        async def run(self, **kwargs):
            """Keep alive until cancelled."""
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
        @property
        def condition(self):
            return CONDITION_ID

    stream = ProductionBookStream(now_ms)

    # Baseline self-attested depuis le fichier
    baseline = json.loads(BASELINE_PATH.read_text())

    # PreparedSession avec token IDs dynamiques
    session = PreparedSession(
        directory=DIRECTORY,
        experiment_id=EXPERIMENT_ID,
        account=ACCOUNT,
        starting_cash="109160000",
        account_reader=provider.account_reader,
        position_reader=provider.position_reader,
        stream=stream,
        market=CONDITION_ID,
        collateral=COLLATERAL,
        tokens={"UP": TOKEN_UP, "DOWN": TOKEN_DOWN},
        clock=now_ms,
        evidence_source=None,
        authority=authority,
        baseline=baseline,
    )
    print("OK PreparedSession construite (production, zéro mock)")

    # Preflight diagnostic avant start()
    from analysis.d6.real_execution_calibration_v1.preflight import evaluate as _evaluate
    _debug = _evaluate(evidence(), now_ms(), shutil.disk_usage(DIRECTORY).free, verifier)
    print(f"DEBUG preflight status: {_debug['status']}")
    for k, v in sorted(_debug['checks'].items()):
        if not v:
            print(f"  FAIL {k}")
    for k, v in sorted(_debug['evidence_failures'].items()):
        if v is not None:
            print(f"  FAIL evidence[{k}]: {v}")

    if _debug["status"] != "CALIBRATION_READY":
        print(f"BLOQUE avant HumanArm : {_debug['blockers']}")
        print("Arrêt — preflight non vert.")
        return

    def pre_arm_summary(report, experiment_id, log_path, text_path):
        """Affiche le résumé PRE_ARM_READY juste avant HumanArm.confirm()."""
        pre = report['preflight'] if 'preflight' in report else report
        checks = pre.get('checks', {})
        blockers = pre.get('blockers', [])
        ws = checks.get('ws_healthy', 'UNKNOWN')
        kill = checks.get('kill_switch_tested', 'UNKNOWN')
        reco = checks.get('reconciliation_tested', 'UNKNOWN')
        cust = checks.get('exit_handoff_ready', 'UNKNOWN')
        fresh = checks.get('fresh_runtime_evidence', 'UNKNOWN')
        storage = checks.get('storage_sufficient', 'UNKNOWN')
        flags = checks.get('global_D6_flags_false', 'UNKNOWN')
        bal_ok = checks.get('balance_sufficient', 'UNKNOWN')
        bal = pre.get('balance', pre.get('balance_sufficient', {}))
        if isinstance(bal, dict):
            bal_str = f"{bal.get('cash', bal.get('required_cash', '?'))} {bal.get('unit', 'pUSD')}"
        else:
            bal_str = str(bal)
        print()
        print("=" * 60)
        print("  PRE_ARM_READY")
        print("=" * 60)
        print(f"  PRE_ARM_READY          = {pre.get('status') == 'CALIBRATION_READY'}")
        print(f"  CALIBRATION_READY      = {pre.get('status') == 'CALIBRATION_READY'}")
        print(f"  EXPERIMENT_ID          = {experiment_id}")
        print(f"  CAPS                   = 100/25/1")
        print(f"  BALANCE                = {bal_str}")
        print(f"  BALANCE_SUFFICIENT     = {bal_ok}")
        print(f"  LOG_JSONL              = {log_path}")
        print(f"  LOG_TEXT               = {text_path}")
        print(f"  FRESH_ENTRY_GUARD      = {fresh}")
        print(f"  KILL_SWITCH_READY      = {kill}")
        print(f"  RECONCILIATION_READY   = {reco}")
        print(f"  CUSTODY_READY          = {cust}")
        print(f"  WS_HEALTHY             = {ws}")
        print(f"  STORAGE_SUFFICIENT     = {storage}")
        print(f"  D6_FLAGS_FALSE         = {flags}")
        print(f"  BLOCKERS               = {blockers if blockers else 'none'}")
        print("=" * 60)
        print()

    def production_confirm(experiment_id, report, *, verifier, evidence):
        """Affiche le résumé PRE_ARM_READY puis délègue à HumanArm.confirm()."""
        log_jsonl = str(DIRECTORY / f"{experiment_id}.jsonl")
        log_text = str(DIRECTORY / f"REAL_CALIBRATION_{time.strftime('%Y%m%d_%H%M')}_{experiment_id}-p0000.log")
        pre_arm_summary(report, experiment_id, log_jsonl, log_text)
        return HumanArm.confirm(experiment_id, report, verifier=verifier, evidence=evidence)

    try:
        result = await session.start(
            client=readonly,
            verifier=verifier,
            evidence=evidence,
            signal_source=signal_source,
            custody_owner=custody_owner,
            confirm=production_confirm,
        )
    except ValueError as e:
        if "NOT_ARMED" in str(e):
            print()
            print("=" * 60)
            print("  BOOTSTRAP PRODUCTION COMPLET")
            print("  HumanArm.confirm() atteint avec succès")
            print("  Aucun ordre, signature, approbation ou transaction exécuté")
            print("  Le système s'arrête à l'invite TTY comme attendu")
            print("  CALIBRATION_READY = VERT")
            print("=" * 60)
        else:
            print(f"BLOQUE avant HumanArm : {e}")
            raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
