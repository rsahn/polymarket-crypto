"""Derive a proposed policy from PUBLIC bootstrap material. Never approve/sign."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from eth_keys import keys
from analysis.d6.real_execution_calibration_v1.core import digest


def proposal(public, expected_sid, session):
    if (not expected_sid.startswith('S-1-5-21-') or public['authority_sid'] != expected_sid
        or expected_sid == public['supervisor_sid'] or public['approved'] is not False
        or public['dpapi_roundtrip'] is not True or public['wallet_secret_access_denied'] is not True
        or not session or session.startswith('PENDING')):
        raise ValueError('PUBLIC_BOOTSTRAP_CONTEXT')
    point=public['public_key']
    if not point.startswith('0x04') or len(point)!=132:raise ValueError('PUBLIC_KEY')
    address=keys.PublicKey(bytes.fromhex(point[4:])).to_checksum_address()
    policy=dict(keys={'d6-windows-telemetry-'+public['key_version']:dict(address=address,kinds=['clock_sanity','ws_healthy'])},
        provider='D6_WINDOWS_INDEPENDENT_TELEMETRY',context=dict(
            account='0x871d37B430C42DDBD0BBD37C29c02A2974109DE9',
            signer='0x9348eFd557A09e644795C8F114BcF0BeF86F203a',collateral='pUSD',session=session))
    return dict(policy=policy,policy_digest=digest(policy),public_key=point,authority_sid=expected_sid,
                approved=False,source_trust_approved=False,isolation_test_required=True,
                consequences='Only the two listed telemetry kinds; no account completeness, funds, orders or custody acceptance.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public-identity',required=True);p.add_argument('--expected-sid',required=True)
    p.add_argument('--session',required=True);p.add_argument('--output',required=True)
    args=p.parse_args()
    result=proposal(json.loads(Path(args.public_identity).read_text(encoding='utf-8-sig')),args.expected_sid,args.session)
    with Path(args.output).open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(policy_digest=result['policy_digest'],approved=False)))
