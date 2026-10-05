"""Restricted signing boundary for independently operated clock/book producers.

No default key, policy, approval, account evidence or order capability.
The operator must separately approve and isolate the producer principal.
"""
import copy
import json
import os
from pathlib import Path
import uuid

from eth_account.messages import encode_defunct
from analysis.d6.real_execution_calibration_v1.core import digest, encoded
from analysis.d6.real_execution_calibration_v1.production_authority import ProductionAuthority
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier

KINDS = frozenset(('clock_sanity', 'ws_healthy'))


class TelemetrySigner:
    def __init__(self, *, policy, approved_digest, key_id, key, context, now):
        if not approved_digest or digest(policy) != approved_digest:
            raise ValueError('EXPLICIT_APPROVED_POLICY_DIGEST_REQUIRED')
        spec = policy['keys'][key_id]
        if set(spec['kinds']) != KINDS or key.address.lower() != spec['address'].lower():
            raise ValueError('RESTRICTED_TELEMETRY_KEY_REQUIRED')
        if any(context.get(k) != v for k, v in policy['context'].items()):
            raise ValueError('POLICY_CONTEXT')
        self.policy, self.context = copy.deepcopy(policy), copy.deepcopy(context)
        self.key, self.key_id, self.now, self.approved_digest = key, key_id, now, approved_digest
        self.authority = ProductionAuthority(keys=policy['keys'], provider=policy['provider'],
            context=policy['context'], clock=now, approval_digest=approved_digest)
        self.verifier = EvidenceVerifier(self.authority, **{k:context[k] for k in
            ('account', 'market', 'session', 'collateral', 'strategy_hashes')})

    def _sign(self, check, payload, observed, until):
        if check not in KINDS:
            raise ValueError('TELEMETRY_ONLY')
        record = dict(self.context, check=check, kind=check, provider=self.policy['provider'],
                      key_id=self.key_id, trust_policy_digest=self.approved_digest,
                      payload=copy.deepcopy(payload), source_digest=digest(payload),
                      observed_ms=observed, valid_until_ms=until)
        record['provenance_signature'] = self.key.sign_message(
            encode_defunct(text='D6_PROVENANCE_V1:'+encoded(record))).signature.hex()
        self.verifier.validate(check, record, self.now())
        return record

    def clock(self, lease):
        candidate = lease.read()  # Rechecks monotonic expiry and wall-clock steps.
        return self._sign('clock_sanity', candidate['payload'], candidate['observed_ms'],
                          candidate['valid_until_ms'])

    def book(self, stream):
        from app.live.readonly_book_stream import StreamBook
        if type(stream) is not StreamBook:
            raise ValueError('REAL_STREAMBOOK_REQUIRED')
        state = stream.read()
        now = self.now()
        if (stream.condition != self.context['market'] or not state['available']
            or state['state'] != 'SYNCHRONIZED' or state.get('reason')):
            raise ValueError('BOOK_UNQUALIFIED')
        stamps = [v['observed_ms'] for v in stream.books.values()]
        receive = state['last_valid_book_received_ms']
        if len(stamps) != 2 or not all(0 <= now-s <= 500 for s in stamps):
            raise ValueError('BOOK_STALE')
        return self._sign('ws_healthy', dict(state='SYNCHRONIZED', generation=state['generation'],
            tokens=list(stream.expected_tokens), receive_ms=receive), now,
            min(min(stamps)+500, stream.expiry, now+500))


def publish_subset(directory, records, now):
    """Dedicated file: never overwrite another producer's qualification records."""
    target = Path(directory).resolve(strict=True)
    if any((p/'.git').exists() for p in (target, *target.parents)):
        raise ValueError('OUTSIDE_GIT_REQUIRED')
    if set(records)-KINDS:
        raise ValueError('TELEMETRY_ONLY')
    body = encoded(dict(observed_ms=now, **records))
    temporary = target/('telemetry-'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x', encoding='utf-8') as f:
        f.write(body); f.flush(); os.fsync(f.fileno())
    os.replace(temporary, target/'telemetry.json')


async def run_telemetry(*, signer, stream, lease, sample_clock, directory, stop):
    """Caller supplies a real running StreamBook and explicitly approved signer.

    This owns only telemetry.json; a verifier must merge authenticated records.
    Source trust/isolation approval cannot be inferred from possession of a key.
    """
    import asyncio
    from contextlib import suppress
    async def refresh():
        while not stop.is_set():
            lease.invalidate()
            try:
                samples = await asyncio.to_thread(sample_clock)
                lease.update(samples)
            except Exception:
                lease.invalidate()
            await asyncio.sleep(.5)
    task = asyncio.create_task(refresh(), name='independent-clock-measurement')
    try:
        while not stop.is_set():
            if task.done():
                task.result()
                raise RuntimeError('CLOCK_PRODUCER_ENDED')
            records = {}
            try:
                records['clock_sanity'] = signer.clock(lease)
                records['ws_healthy'] = signer.book(stream)
            except ValueError:
                records = {}  # Withdraw both if clock/book becomes unusable.
            publish_subset(directory, records, signer.now())
            await asyncio.sleep(.1)
    finally:
        task.cancel()
        try:
            with suppress(asyncio.CancelledError):
                await task
        finally:
            publish_subset(directory, {}, signer.now())
