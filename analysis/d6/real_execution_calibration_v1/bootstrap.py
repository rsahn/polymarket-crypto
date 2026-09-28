"""Bootstrap minimal — assemble les 5 dépendances réelles qualifiées,
teste le chemin complet hors argent jusqu'à HumanArm.confirm().
"""
import asyncio, copy, io, json, shutil, sys, time
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from analysis.d6.real_execution_calibration_v1.runner import PreparedSession, SignalSource
from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority, evidence as evidence_fn
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier
from analysis.d6.real_execution_calibration_v1.custody import CustodyOwner, ReceiptVerifier, CustodyStateStore
from analysis.d6.real_execution_calibration_v1.v1_binding import verify as v1_verify

# ─── Ponts de wiring (pas de nouvelle fonctionnalité) ────────────────────────
class BootstrapAuthority(SelfAttestingAuthority):
    """Wrapper minimal : ajoute verify_client et verify_bindings."""
    def verify_client(self, client, proof):
        return True
    def verify_bindings(self, bindings, proof):
        return True

# ─── Dépendance 1 : client (structurel, pas de credentials) ─────────────────
class MockClient:
    wallet = '0x871d37b430c42ddbd0bbd37c29c02a2974109de9'
    signer = '0x9348efd557a09e644795c8f114bcf0bef86f203a'
    environment = 'production'
    signature_type = 3

class MockReader:
    def __init__(self, row):
        self.row = row
    async def read(self):
        return copy.deepcopy(self.row)
    async def order(self, order_id):
        return {'available': True, 'order': {'id': order_id}}

# ─── Dépendance 2 : verifier ────────────────────────────────────────────────
CONDITION_ID = '0xc2bce096198c6f4c16bcefa91cc16829f8a84bf9e20551b8147d72c8bc6f5433'
TOKEN_UP = '108356011342159985803141201944072402866666559766806853187422737531686424103314'
TOKEN_DOWN = '16759512213770205038300183826897320054770267440645397738685477740352888131801'
ACCOUNT = '0x871d37b430c42ddbd0bbd37c29c02a2974109de9'
SIGNER = '0x9348efd557a09e644795c8f114bcf0bef86f203a'
COLLATERAL = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
CASH = '109160000'
REQUIRED_CASH = '100000000'

STRATEGY_HASHES = v1_verify()

authority = BootstrapAuthority()
verifier = EvidenceVerifier(
    authority,
    account=ACCOUNT,
    market=CONDITION_ID,
    session='calibration-bootstrap',
    collateral=COLLATERAL,
    strategy_hashes=STRATEGY_HASHES,
)

# ─── Dépendance 3 : evidence callable (session synchronisée) ────────────────
from analysis.d6.real_execution_calibration_v1.evidence import build_evidence as _build_evidence

BASELINE_DIGEST = '46b72832b1480d2c6532d143c524ee8ebe289bb18f3f3ded3b8e10858d2263e4'

def evidence():
    """Wrapper qui aligne la session et le owner sur le verifier/custody."""
    return _build_evidence(
        experiment_id='calibration-bootstrap',
        owner='operator',
        baseline_digest=BASELINE_DIGEST,
    )

# ─── Dépendance 4 : signal_source ───────────────────────────────────────────
signal_source = SignalSource(collector_factory=None)

# ─── Dépendance 5 : custody_owner ───────────────────────────────────────────
class MockChannel:
    async def accept(self, request):
        return dict(
            **request,
            owner='operator',
            receipt_id='bootstrap-receipt',
            accepted_ms=int(time.time() * 1000),
            future_result_client_ids=list(request.get('exposure', {}).get('orders', [])),
        )

class MockDurableAuthority:
    async def verify_durable(self, r):
        return True

receipt_verifier = ReceiptVerifier(
    MockDurableAuthority(),
    'operator',
    clock=lambda: int(time.time() * 1000),
)
custody_owner = CustodyOwner(MockChannel(), receipt_verifier, state_store=None)

# ─── StreamBook mocké (pas de WS réel) ──────────────────────────────────────
from backend.app.live.production_readonly import BookStateSource

class MockBookSource(BookStateSource):
    """BookStateSource avec données injectées, sans WS."""
    def __init__(self, slug, condition, tokens, expiry, *, clock):
        super().__init__(clock=clock)
        self.slug = slug
        self.condition = condition
        self.expected_tokens = tuple(tokens)
        self.expiry = expiry
        # Connect and inject both books immediately
        self.connect(slug, self.expected_tokens, 1)
        now = clock()
        for t in tokens:
            self.update(t,
                [['0.45', '100'], ['0.44', '50']],
                [['0.55', '100'], ['0.56', '50']],
                now, 1)

    def read(self):
        """Refresh timestamps on each read to stay within BOOK_MAX_AGE_MS."""
        now = self.clock()
        for t in self.expected_tokens:
            b = self.books.get(t)
            if b:
                b['observed_ms'] = now
        return super().read()

    async def run(self):
        """Keep alive until cancelled so BookAdapter can detect healthy state."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


async def main():
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    session = None
    try:
        now_ms = lambda: int(time.time() * 1000)

        account_reader = MockReader({
            'available': True,
            'wallet': ACCOUNT,
            'collateral_symbol': 'pUSD',
            'observed_ms': now_ms(),
            'balance_collateral': CASH,
            'open_order_ids': [],
            'trade_ids': [],
            'complete': True,
            'pagination_complete': True,
        })
        position_reader = MockReader({
            'available': True,
            'wallet': ACCOUNT,
            'collateral_symbol': 'pUSD',
            'observed_ms': now_ms(),
            'balances': {},
            'complete': True,
        })

        stream = MockBookSource(
            'btc-updown-5m-1790516400',
            CONDITION_ID,
            [TOKEN_UP, TOKEN_DOWN],
            10000,
            clock=now_ms,
        )

        # Static baseline that matches BASELINE_DIGEST used in evidence()
        baseline = {'version': 'REAL_EXECUTION_CALIBRATION_V1', 'started': 1790577000000}
        session = PreparedSession(
            directory=tmp,
            experiment_id='calibration-bootstrap',
            account=ACCOUNT,
            starting_cash=CASH,
            account_reader=account_reader,
            position_reader=position_reader,
            stream=stream,
            market=CONDITION_ID,
            collateral=COLLATERAL,
            tokens={'UP': TOKEN_UP, 'DOWN': TOKEN_DOWN},
            clock=now_ms,
            baseline=baseline,
        )
        print("OK PreparedSession construite")

        # ─── Mock confirm : intercepte à la porte HumanArm ──────────────────
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
            print("  > Invite TTY : Type CALIBRATE {experiment_id} to arm this process")
            print("  > Aucune saisie - arret au gate.")
            print()
            raise ValueError('NOT_ARMED')

        try:
            # Debug: inspect preflight before start
            import shutil as _shutil
            from analysis.d6.real_execution_calibration_v1.preflight import evaluate as _evaluate
            _debug = _evaluate(evidence(), now_ms(), _shutil.disk_usage(tmp).free, verifier)
            print("DEBUG preflight status:", _debug['status'])
            for k, v in sorted(_debug['checks'].items()):
                if not v:
                    print(f"  FAIL {k}")
            for k, v in sorted(_debug['evidence_failures'].items()):
                if v is not None:
                    print(f"  FAIL evidence[{k}]: {v}")

            result = await session.start(
                client=MockClient(),
                verifier=verifier,
                evidence=evidence,
                signal_source=signal_source,
                custody_owner=custody_owner,
                confirm=mock_confirm,
            )
        except ValueError as e:
            if 'NOT_ARMED' in str(e) and HUMAN_ARM_REACHED:
                print("OK Bootstrap complet : HumanArm.confirm() atteint avec succes")
                print("OK Aucun ordre, aucune signature, aucune transaction")
                print("OK Le systeme s'arrete a l'invite TTY comme attendu")
            else:
                if not HUMAN_ARM_REACHED:
                    print(f"BLOQUE avant HumanArm : {e}")
                raise

    finally:
        if session is not None:
            try:
                session.close()
            except RuntimeError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
