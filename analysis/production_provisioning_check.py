"""Read-only provisioning diagnostics; never constructs a trading client or arms.

Runs the 14 evidence predicates and the production storage check. This is not
the launch's runtime assembly/WS/custody probe and can never grant LIVE_GATE.
Only public policy/evidence files are read; no credentials are loaded.
"""
import argparse
import asyncio
import json
from importlib.metadata import version
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
from analysis.d6.real_execution_calibration_v1 import preflight
from analysis.d6.real_execution_calibration_v1.capacity import require_capacity
from analysis.d6.real_execution_calibration_v1.core import digest
from analysis.d6.real_execution_calibration_v1.production_provider import EvidenceInbox
from analysis.d6.real_execution_calibration_v1.production_authority import ProductionAuthority
from analysis.d6.real_execution_calibration_v1.production_evidence_source import ProductionEvidenceSource
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier
from analysis.d6.real_execution_calibration_v1.adapters import AccountAdapter


async def inspect(args):
    now = lambda: time.time_ns() // 1000000
    evidence, verifier = {}, None
    checks, errors = {}, {}

    def check(name, fn):
        try:
            result = fn()
            checks[name] = True
            return result
        except Exception as exc:
            checks[name] = False
            # Never expose arbitrary provider payloads or exception messages.
            errors[name] = type(exc).__name__
            return None

    check('frozen_v1', preflight.verify)
    sdk = check('sdk_version', lambda: version('polymarket-client'))
    checks['sdk_version'] = sdk == '0.11.0'
    capacity = check('production_storage', lambda: require_capacity(args.log_directory))
    inbox = check('inbox_present', lambda: EvidenceInbox(args.inbox)) if args.inbox else None
    checks.setdefault('inbox_present', False)
    authority = None
    if inbox and args.policy and args.approved_policy_digest:
        def load_authority():
            # Reuse bounded, duplicate-key-rejecting outside-Git reader.
            policy_path = Path(args.policy).resolve(strict=True)
            policy = EvidenceInbox(policy_path.parent).read(policy_path.name)
            if digest(policy) != args.approved_policy_digest:
                raise ValueError('POLICY_DIGEST_MISMATCH')
            if set(policy['context']) != {'account', 'signer', 'collateral', 'session'}:
                raise ValueError('POLICY_CONTEXT_REQUIRED')
            return ProductionAuthority(keys=policy['keys'], provider=policy['provider'],
                context=policy['context'], clock=now, approval_digest=args.approved_policy_digest)
        authority = check('policy_digest_and_shape', load_authority)
    checks.setdefault('policy_digest_and_shape', False)
    checks['external_policy_approval_independently_verified'] = False
    if authority:
        def load_verifier():
            market = inbox.read('market.json')
            ctx = authority.context
            return EvidenceVerifier(authority, account=ctx['account'], session=ctx['session'],
                collateral=ctx['collateral'], market=market['condition_id'], strategy_hashes=preflight.verify())
        verifier = check('verifier_context', load_verifier)
        loaded = check('qualification_file', inbox.qualification)
        if isinstance(loaded, dict):
            evidence = loaded
        def load_source():
            ctx = authority.context
            return ProductionEvidenceSource(inbox, authority=authority, account=ctx['account'],
                collateral=ctx['collateral'], session=ctx['session'], baseline=inbox.baseline(), clock=now)
        source = check('baseline_consumer_contract', load_source)
        if source:
            try:
                adapter = AccountAdapter(None, None, account=source.account, collateral=source.collateral,
                    evidence_source=source, authority=authority, baseline=source.baseline,
                    session=source.session, clock=now)
                await adapter.snapshot()
                checks['snapshot_consumer_contract'] = True
            except Exception as exc:
                checks['snapshot_consumer_contract'] = False
                errors['snapshot_consumer_contract'] = type(exc).__name__
    free = check('storage_readable', lambda: shutil.disk_usage(args.log_directory).free)
    report = preflight.evaluate(evidence, now(), free or 0, verifier=verifier)
    count = sum(report['checks'][k] for k in preflight.REQUIRED)
    return dict(schema='production-provisioning-diagnostic/v1', observed_ms=now(),
        local_checks=checks, local_errors=errors, production_capacity=capacity,
        sdk_version=sdk, evidence_preflight=report, PREFLIGHT_PROOFS=f'{count}/14',
        LIVE_GATE='BLOCKED', HUMAN_ARM_REQUIRED=True, armed=False, submit_allowed=False,
        full_production_preflight_completed=False,
        outstanding=['Independent provider coverage/archive approval',
                     'Independent trust-policy approval and live signer operation',
                     'Bound SDK identity, real StreamBook and launch validate_assembly',
                     'Independent durable custody acceptance and supervisor-death probe',
                     'Interactive HumanArm only after all preceding checks pass'],
        limitation='A policy digest match authenticates bytes, not external approval. '
                   'Consumer contracts do not prove real-world wallet completeness. '
                   'No execution envelope is requested and no order is sent.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inbox')
    parser.add_argument('--policy')
    parser.add_argument('--approved-policy-digest')
    parser.add_argument('--log-directory', default='D:/polymarket-real-calibration/live')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = asyncio.run(inspect(args))
    # Exclusive creation preserves earlier diagnostics; reports are not evidence.
    with Path(args.output).open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps({k: result[k] for k in ('PREFLIGHT_PROOFS', 'LIVE_GATE', 'full_production_preflight_completed')}))
    return 2  # Diagnostics never authorize production, even with 14 valid records.


if __name__ == '__main__':
    raise SystemExit(main())
