"""Explicit non-armed composition root; imports never construct an SDK.
This revision is preparation-only. No CLI switch can enable submission.
"""
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class SessionContext:
    account:str
    session:str
    market:str
    collateral:str | None
    up:str
    down:str
    baseline_digest:str | None
from .adapters import AccountAdapter,BookAdapter
from .core import CalibrationLedger
from .engine import Coordinator
from .live_logging import LoggedJournal,LiveLog
from .preflight import evaluate

class DisabledPort:
    async def prepare(self,**kwargs):raise ValueError('LIVE_QUALIFICATION_REQUIRED')
    async def submit_once(self,*args):raise ValueError('LIVE_QUALIFICATION_REQUIRED')

class PreparedSession:
    def __init__(self,*,directory,experiment_id,account,starting_cash,account_reader,position_reader,stream,market,tokens,clock,collateral=None,evidence_source=None,authority=None,baseline=None):
        from .core import digest
        self.context=SessionContext(account,experiment_id,market,collateral,tokens['UP'],tokens['DOWN'],digest(baseline) if baseline else None)
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.log=LiveLog(self.directory,experiment_id);self.log.public_tokens.update(tokens.values());self.log.public_markets.add(market)
        try:
            self.journal=LoggedJournal(self.directory/(experiment_id+'.jsonl'),experiment_id,self.log)
            self.ledger=CalibrationLedger(self.journal,account,starting_cash)
            self.account=AccountAdapter(account_reader,position_reader,account=account,collateral=collateral,evidence_source=evidence_source,authority=authority,baseline=baseline,session=experiment_id,intents=lambda:self.ledger.orders,clock=clock)
            self.book=BookAdapter(stream,market=market,tokens=tokens,clock=clock)
            def fault(reason):
                self.ledger.stop=True;self.ledger.reconciled=False;self.ledger.reasons.append(reason)
            self.log.on_fault=fault
            self.coordinator=Coordinator(self.ledger,DisabledPort(),self.account,self.book,self.directory/'STOP',clock=clock)
        except BaseException:
            if hasattr(self,'journal'):self.journal.close()
            self.log.close();raise
    def close(self):
        owner=getattr(self,'custody_owner',None)
        if owner and (owner.tasks or owner.operations or any(v!='TRANSFERRED' for v in owner.states.values())):raise RuntimeError('CUSTODY_STILL_OWNED')
        self.journal.close();self.log.close()
    def validate_assembly(self,verifier,proof,client,owner):
        from .core import digest,dec
        ctx=verifier.context
        expected=dict(account=self.context.account,session=self.context.session,market=self.context.market,collateral=self.context.collateral)
        actual=dict(account=self.ledger.account,session=self.journal.experiment_id,market=self.book.market,collateral=self.account.collateral)
        if actual!=expected or self.book.tokens!={'UP':self.context.up,'DOWN':self.context.down}:raise ValueError('ASSEMBLY_CONTEXT_MUTATED')
        if digest(self.account.baseline)!=self.context.baseline_digest:raise ValueError('ASSEMBLY_BASELINE_MUTATED')
        if any(ctx.get(k)!=v for k,v in expected.items()):raise ValueError('ASSEMBLY_CONTEXT_MISMATCH')
        market=proof['market_identity_verified']['payload']
        if market.get('outcome_tokens')!=self.book.tokens:raise ValueError('ASSEMBLY_OUTCOME_MAPPING')
        if market['tokens']!=[self.book.tokens['UP'],self.book.tokens['DOWN']] or proof['ws_healthy']['payload']['tokens']!=market['tokens']:raise ValueError('ASSEMBLY_TOKEN_ORDER')
        bindings=(verifier.authority,owner.channel,owner.verifier.authority,self.account.evidence_source,self.account.authority)
        method=getattr(verifier.authority,'verify_bindings',None)
        if method is None or method(bindings,proof) is not True:raise ValueError('ASSEMBLY_PROVIDER_BINDINGS')
        if hasattr(self,'provider_bindings') and any(a is not b for a,b in zip(self.provider_bindings,bindings)):raise ValueError('ASSEMBLY_PROVIDER_REPLACED')
        self.provider_bindings=bindings
        if proof['exit_handoff_ready']['payload']['owner']!=owner.verifier.owner:raise ValueError('ASSEMBLY_CUSTODY_OWNER')
        if not self.account.baseline or proof['account_evidence_adapter_qualified']['payload']['baseline_digest']!=digest(self.account.baseline):raise ValueError('ASSEMBLY_BASELINE')
        if dec(proof['balance_sufficient']['payload']['required_cash'])<self.ledger.MAX_TOTAL:raise ValueError('ASSEMBLY_REQUIRED_BUDGET')
        # Authority must bind this very client instance without exposing credentials.
        if verifier.authority.verify_client(client,proof['sdk_order_path_qualified']) is not True:raise ValueError('ASSEMBLY_CLIENT_UNQUALIFIED')

    async def start(self,*,client=None,verifier=None,evidence=None,signal_source=None,custody_owner=None,confirm=None):
        import asyncio,shutil
        from .engine import HumanArm
        from .transport import SDKPort
        from .qualification import FeeRisk
        from .supervisor import run
        if any(x is None for x in (client,verifier,evidence,signal_source,custody_owner)):raise ValueError('LIVE_DEPENDENCIES_REQUIRED')
        self.custody_owner=custody_owner
        if confirm is None:
            if self.directory.resolve().drive.lower()!='d:':raise ValueError('LIVE_LOG_TARGET_MUST_BE_D')
            if custody_owner.state_store is None:raise ValueError('DURABLE_CUSTODY_STORE_REQUIRED')
        # Start public book initialization only; no signals or signed-order preparation.
        book_task=asyncio.create_task(self.book.run(self.coordinator.on_status));primary=None;result=None
        try:
            await self.book.wait_ready()
            proof=evidence()
            report=evaluate(proof,self.coordinator.clock(),shutil.disk_usage(self.directory).free,verifier)
            if report['status']!='CALIBRATION_READY':raise ValueError('PREFLIGHT_BLOCKED')
            self.validate_assembly(verifier,proof,client,custody_owner)
            if confirm is None:
                from .readonly_provider import SDKIdentityBinding
                identity=proof['wallet_account_identity_verified']['payload']
                self.sdk_binding=SDKIdentityBinding.inspect(client,wallet=identity['maker'],signer=identity['signer'])
            if self.book.state!='SYNCHRONIZED' or not self.book.stream.read().get('available'):raise ValueError('BOOK_DEGRADED')
            # Refresh evidence and preflight with fresh timestamps for HumanArm.confirm()
            # (validate_assembly + SDKIdentityBinding.inspect may have consumed >5s)
            proof=evidence()
            import shutil as _shutil
            report=evaluate(proof,self.coordinator.clock(),_shutil.disk_usage(self.directory).free,verifier)
            if report['status']!='CALIBRATION_READY':raise ValueError('PREFLIGHT_REFRESH_BLOCKED: '+' '.join(report['blockers']))
            arm=(confirm or HumanArm.confirm)(self.journal.experiment_id,report,verifier=verifier,evidence=proof)
            fee=verifier.validate('fee_upper_bound_proven',proof['fee_upper_bound_proven'],self.coordinator.clock())
            def current_fee():
                current=evidence();record=current['fee_upper_bound_proven']
                fee=verifier.validate('fee_upper_bound_proven',record,self.coordinator.clock())
                return FeeRisk(fee['cash_collateral'],fee['outcome_shares'],fee['collateral_per_share_upper'],fee['fee_source_digest'],verifier.context['market'],record['valid_until_ms'],fee['epoch'])
            self.coordinator.fee_ceiling=current_fee
            identity=verifier.validate('wallet_account_identity_verified',proof['wallet_account_identity_verified'],self.coordinator.clock())
            self.coordinator.arm=arm
            human_arm=arm
            class RevalidatedArm:
                nonce=arm.nonce
                started_monotonic=arm.started_monotonic
                def check(inner,session,entry=True):
                    human_arm.check(session,entry)
                    current=evidence()
                    self.validate_assembly(verifier,current,client,custody_owner)
                    if hasattr(self,'sdk_binding') and not self.sdk_binding.matches(client):raise ValueError('SDK_PUBLIC_IDENTITY_CHANGED')
                    fresh=evaluate(current,self.coordinator.clock(),shutil.disk_usage(self.directory).free,verifier)
                    if fresh['status']!='CALIBRATION_READY':raise ValueError('RUNTIME_EVIDENCE_INVALID')
            arm=RevalidatedArm()
            self.coordinator.arm=arm
            self.coordinator.port=SDKPort(client,maker=identity['maker'],signer=identity['signer'],ledger=self.ledger,arm=arm,qualified=True)
            class RunningBook:
                async def run(inner,on_status):await asyncio.shield(book_task)
            result=await run(self.coordinator,signal_source,RunningBook(),self.directory/'reports',custody_owner)
        except BaseException as exc:primary=exc
        finally:
            try:await custody_owner.wait_resolved()
            except BaseException as exc:
                if primary is None:primary=exc
                else:custody_owner.errors.append('ROOT_CLEANUP:'+type(exc).__name__)
            book_task.cancel()
            while not book_task.done():
                try:await asyncio.wait({book_task},timeout=.1)
                except asyncio.CancelledError:continue
            if not book_task.cancelled():
                try:book_task.result()
                except BaseException as exc:
                    if primary is None:primary=exc
            await self.book.shutdown()
        if primary is not None:raise primary
        return result

class SignalSource:
    def __init__(self,collector_factory=None):self.collector_factory=collector_factory
    async def run(self,on_tick,on_status):
        factory=self.collector_factory
        if factory is None:
            from app.collectors.binance import BinanceCollector
            factory=BinanceCollector
        async def status(kind,details):
            if kind!='BTC_CONNECTED':on_status('WS_DISCONNECT')
        await factory('btcusdt',on_tick,status).run()

def prepare_report(evidence,now_ms,free_bytes):
    # Deliberately does not create PreparedSession, files, a client or signed orders.
    return evaluate(evidence,now_ms,free_bytes)

DEFAULT_DIRECTORY=Path('D:/polymarket-real-calibration/preparation')
