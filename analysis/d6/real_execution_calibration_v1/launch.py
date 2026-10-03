"""Production composition, requiring independently provisioned dependencies.

No account discovery, credentials, signatures or network work at import. Call
main with an approved provider/authority/baseline, real SDK client and durable
custody owner. HumanArm remains the final, interactive gate.
"""
from pathlib import Path
import time
from .runner import PreparedSession,SignalSource
from .production_authority import ProductionAuthority
from .production_evidence_source import ProductionEvidenceSource
from .qualification import EvidenceVerifier
from .v1_binding import verify
from .core import digest
DIRECTORY=Path('D:/polymarket-real-calibration/live')

async def main(*, authority=None,provider=None,baseline=None,client=None,custody=None,
               market=None,evidence=None,rotation_source=None,directory=DIRECTORY):
    if any(v is None for v in (authority,provider,baseline,client,custody,market,evidence,rotation_source)):
        raise RuntimeError('LIVE_GATE_BLOCKED: externally approved trust policy, full-wallet provider/baseline, fresh qualification proofs, SDK identity and durable custody required')
    if type(authority) is not ProductionAuthority:raise ValueError('PRODUCTION_AUTHORITY_REQUIRED')
    from polymarket.clients.async_secure import AsyncSecureClient
    from app.live.readonly_book_stream import StreamBook
    if type(client) is not AsyncSecureClient:raise ValueError('PRODUCTION_SDK_REQUIRED')
    if custody.state_store is None:raise ValueError('DURABLE_CUSTODY_STORE_REQUIRED')
    clock=lambda:time.time_ns()//1000000
    ctx=authority.context
    source=ProductionEvidenceSource(provider,authority=authority,account=ctx['account'],collateral=ctx['collateral'],session=ctx['session'],baseline=baseline,clock=clock)
    authority.bind(client=client,source=source,custody=custody)
    tokens=market['outcome_tokens']
    if set(tokens)!={'UP','DOWN'} or tokens['UP']==tokens['DOWN'] or market['expiry_ms']<=clock():raise ValueError('MARKET_IDENTITY')
    stream=StreamBook(market['slug'],market['condition_id'],(tokens['UP'],tokens['DOWN']),market['expiry_ms'],clock=clock)
    verifier=EvidenceVerifier(authority,account=ctx['account'],market=market['condition_id'],session=ctx['session'],collateral=ctx['collateral'],strategy_hashes=verify())
    session=PreparedSession(directory=directory,experiment_id=ctx['session'],account=ctx['account'],starting_cash=baseline['cash'],account_reader=None,position_reader=None,stream=stream,market=market['condition_id'],tokens=tokens,clock=clock,collateral=ctx['collateral'],evidence_source=source,authority=authority,baseline=baseline,production_capacity=True)
    try:
        return await session.start(client=client,verifier=verifier,evidence=evidence,signal_source=SignalSource(),custody_owner=custody,rotation_source=rotation_source)
    finally:session.close()

if __name__=='__main__':
    import asyncio
    asyncio.run(main())


async def from_approved_inbox(*,directory,trust_policy,approved_policy_digest,client,custody,log_directory=DIRECTORY):
    """The approved digest must come from the operator's independent review.
    A digest calculated automatically from the same local file is not approval.
    """
    from .production_provider import EvidenceInbox
    if digest(trust_policy)!=approved_policy_digest:raise ValueError('TRUST_POLICY_APPROVAL_MISMATCH')
    inbox=EvidenceInbox(directory)
    authority=ProductionAuthority(keys=trust_policy['keys'],provider=trust_policy['provider'],context=trust_policy['context'],clock=lambda:time.time_ns()//1000000,approval_digest=approved_policy_digest)
    return await main(authority=authority,provider=inbox,baseline=inbox.baseline(),client=client,custody=custody,market=inbox.read('market.json'),evidence=inbox.qualification,rotation_source=inbox.next_market,directory=log_directory)
