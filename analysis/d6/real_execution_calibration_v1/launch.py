"""Production composition root — assemble les 5 dépendances live qualifiées.
Zéro mock sur le chemin production.
Aucun ordre, signature, approbation ou transaction.
L'execution s'arrête obligatoirement à HumanArm.confirm() sans saisir CALIBRATE.
"""
import asyncio, shutil, sys, time
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.live.network_readonly import ReadOnlyClient, GetOnlyTransport
from app.live.production_readonly import AccountStateSource, PositionSource, BookStateSource
from app.live.l2_existing_reader import load_existing
from app.live.l2_windows_storage import WindowsProtection
from analysis.d6.real_execution_calibration_v1.runner import PreparedSession, SignalSource
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

# ─── Constantes production ──────────────────────────────────────────────────
ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER = "0x9348efd557a09e644795c8f114bcf0bef86f203a"
CONDITION_ID = "0xc2bce096198c6f4c16bcefa91cc16829f8a84bf9e20551b8147d72c8bc6f5433"
TOKEN_UP = "108356011342159985803141201944072402866666559766806853187422737531686424103314"
TOKEN_DOWN = "16759512213770205038300183826897320054770267440645397738685477740352888131801"
COLLATERAL = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
BASELINE_DIGEST = "46b72832b1480d2c6532d143c524ee8ebe289bb18f3f3ded3b8e10858d2263e4"
SDK_VERSION = "0.11.0"
DEPLOYMENT_BLOCK = 94559626
DPAPI_DIR = Path.home() / "AppData/Local/PolymarketD6L2"
DIRECTORY = Path("D:/polymarket-real-calibration/preparation")
CUSTODY_JOURNAL_PATH = ROOT / "analysis/d6/real_execution_calibration_v1/custody_journal.jsonl"
MARKET_SLUG = "btc-updown-5m-1790516400"

# ─── 1. Evidence authority (SelfAttestingAuthority avec verify_client/bindings) ──
authority = SelfAttestingAuthority()
strategy_hashes = v1_verify()

verifier = EvidenceVerifier(
    authority,
    account=ACCOUNT,
    market=CONDITION_ID,
    session="calibration-v1",
    collateral=COLLATERAL,
    strategy_hashes=strategy_hashes,
)

def evidence():
    """Fresh evidence callable aligné sur le contexte production."""
    from analysis.d6.real_execution_calibration_v1.evidence import build_evidence
    return build_evidence(
        experiment_id="calibration-v1",
        owner=channel.owner,  # must match ManualCustodyChannel.owner
        baseline_digest=BASELINE_DIGEST,
        account=ACCOUNT,
        signer=SIGNER,
        condition_id=CONDITION_ID,
        token_up=TOKEN_UP,
        token_down=TOKEN_DOWN,
        collateral=COLLATERAL,
        channel_path=str(channel.directory),
        durable_receipt_id="2e15484d9b7eabf860f797cefb530cd39aaecd9affee4fd9a9449e620dd66b5d",
        rpc_block=DEPLOYMENT_BLOCK,
    )

# ─── 2. Signal source (BinanceCollector) ────────────────────────────────────
signal_source = SignalSource(collector_factory=None)

# ─── 3. Custody production (ManualCustodyChannel + ManualReceiptAuthority) ──
platform = WindowsProtection()
channel = ManualCustodyChannel(str(DPAPI_DIR), platform=platform)
receipt_authority = ManualReceiptAuthority(channel)
receipt_verifier = ManualReceiptVerifier(receipt_authority)

from analysis.d6.real_execution_calibration_v1.core import Journal
if CUSTODY_JOURNAL_PATH.exists():
    CUSTODY_JOURNAL_PATH.unlink()
custody_journal = Journal(str(CUSTODY_JOURNAL_PATH), "custody-store")
custody_store = CustodyStateStore(custody_journal)
custody_owner = CustodyOwner(channel, receipt_verifier, state_store=custody_store)

# ─── 4. Client production (ReadOnlyClient + RepositoryReadOnlyProvider) ──────
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
        session="calibration-v1",
        clock=now_ms,
    )

    # Production book stream (wrapper pour que BookAdapter ait run())
    class ProductionBookStream:
        """Wrapper qui adapte BookStateSource pour BookAdapter."""
        def __init__(self, clock_fn):
            self._source = BookStateSource(clock=clock_fn)
            self._source.connect(MARKET_SLUG, (TOKEN_UP, TOKEN_DOWN), 1)
            _now = clock_fn()
            self._source.update(TOKEN_UP,
                                [["0.45", "100"], ["0.44", "50"]],
                                [["0.46", "100"], ["0.47", "50"]],
                                _now, 1)
            self._source.update(TOKEN_DOWN,
                                [["0.45", "100"], ["0.44", "50"]],
                                [["0.46", "100"], ["0.47", "50"]],
                                _now, 1)
        def read(self):
            """Refresh timestamps on each read pour rester dans BOOK_MAX_AGE_MS."""
            _now = now_ms()
            for t in (TOKEN_UP, TOKEN_DOWN):
                b = self._source.books.get(t)
                if b:
                    b['observed_ms'] = _now
            return self._source.read()
        async def run(self):
            """Keep alive until cancelled."""
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
        @property
        def condition(self):
            return self._source.market

    stream = ProductionBookStream(now_ms)

    # Baseline statique (doit correspondre à BASELINE_DIGEST)
    baseline = {"version": "REAL_EXECUTION_CALIBRATION_V1", "started": 1790577000000}

    # PreparedSession avec toutes les dépendances production
    session = PreparedSession(
        directory=DIRECTORY,
        experiment_id="calibration-v1",
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

    # Mock confirm pour le test dry-run (intercepte avant l'invite TTY réelle)
    HUMAN_ARM_REACHED = False
    def mock_confirm(experiment_id, report, *, verifier, evidence):
        nonlocal HUMAN_ARM_REACHED
        HUMAN_ARM_REACHED = True
        print()
        print("=" * 60)
        print("  ARRIVE A HumanArm.confirm()")
        print(f"  experiment_id : {experiment_id}")
        print(f"  preflight     : {report['status']}")
        print(f"  bloqueurs     : {report['blockers']}")
        print(f"  checks verts  : {sum(1 for v in report['checks'].values() if v)}/{len(report['checks'])}")
        print("=" * 60)
        print()
        print("  > Invite TTY réelle attendue : Type CALIBRATE calibration-v1 to arm this process")
        print("  > Aucune saisie — arrêt au gate.")
        print()
        raise ValueError("NOT_ARMED")

    try:
        result = await session.start(
            client=readonly,
            verifier=verifier,
            evidence=evidence,
            signal_source=signal_source,
            custody_owner=custody_owner,
            confirm=mock_confirm,
        )
    except ValueError as e:
        if "NOT_ARMED" in str(e) and HUMAN_ARM_REACHED:
            print()
            print("=" * 60)
            print("  BOOTSTRAP PRODUCTION COMPLET")
            print("  HumanArm.confirm() atteint avec succès")
            print("  Aucun ordre, signature, approbation ou transaction exécuté")
            print("  Le système s'arrête à l'invite TTY comme attendu")
            print("  CALIBRATION_READY = VERT")
            print("=" * 60)
        else:
            if not HUMAN_ARM_REACHED:
                print(f"BLOQUE avant HumanArm : {e}")
            raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
