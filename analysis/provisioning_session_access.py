"""Owner-authenticated GET-only access inventory. Never grants completeness."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'backend')]
from app.live.network_readonly import GetOnlyTransport
from app.live.l2_existing_reader import load_existing, EXPECTED
from polymarket._internal.hmac import build_hmac_signature
WALLET = '0x871d37B430C42DDBD0BBD37C29c02A2974109DE9'

async def observe():
    credentials, storage = load_existing(ROOT)
    if not credentials:
        raise ValueError('EXISTING_CREDENTIALS_REQUIRED')
    async def headers(path):
        ts = int(time.time())
        return {'POLY_ADDRESS': EXPECTED, 'POLY_API_KEY': credentials['apiKey'],
                'POLY_PASSPHRASE': credentials['passphrase'], 'POLY_TIMESTAMP': str(ts),
                'POLY_SIGNATURE': build_hmac_signature(secret=credentials['secret'],
                    timestamp=ts, method='GET', path=path, body=None)}
    audit = []
    transport = GetOnlyTransport('https://clob.polymarket.com',
        {'/v1/user/session-signers', '/auth/api-keys'}, headers=headers, audit=audit)
    report = dict(wallet=WALLET, owner=EXPECTED, observed_ms=time.time_ns()//1000000,
                  CURRENT_SAFE_STATE_PROVEN=False, historical_access_completeness=False,
                  submit_allowed=False, user_declaration_used_as_proof=False)
    try:
        raw = await transport.get_json('/v1/user/session-signers')
        if not isinstance(raw, dict) or str(raw.get('wallet')).lower()!=WALLET.lower() or type(raw.get('signers')) is not list:
            raise ValueError('SESSION_WALLET_OR_SCHEMA')
        rows = []
        for r in raw['signers']:
            if not isinstance(r,dict) or not isinstance(r.get('address'),str) or not isinstance(r.get('scopes'),list) or type(r.get('valid_until')) is not int:
                raise ValueError('SESSION_ROW_SCHEMA')
            rows.append({k:r[k] for k in ('address','scopes','valid_until')})
        report['active_sessions'] = dict(status='AUTHENTICATED_CURRENT_LIST', count=len(rows), signers=rows,
            canonical_response_sha256=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest())
    except Exception as exc:
        report['active_sessions'] = dict(status='UNPROVEN',error_type=type(exc).__name__)
    try:
        raw = await transport.get_json('/auth/api-keys')
        rows = raw['apiKeys']
        if not isinstance(rows,list) or not all(isinstance(k,str) for k in rows):
            raise ValueError('KEY_LIST_SCHEMA')
        report['owner_credentials'] = dict(status='AUTHENTICATED_CURRENT_LIST',count=len(rows),
            existing_key_listed=credentials['apiKey'] in rows,
            identifiers_logged=False, historical_completeness=False)
    except Exception as exc:
        report['owner_credentials'] = dict(status='UNPROVEN',error_type=type(exc).__name__)
    report['network_audit']=audit
    report['limitations']=['Active sessions omit expired/revoked keys and their residual settlements.',
        'Owner credentials cannot enumerate session-key orders.',
        'No historical lifecycle, common account/chain cut or absence of residual liabilities proven.']
    return report

if __name__ == '__main__':
    report = asyncio.run(observe())
    with Path(sys.argv[1]).open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2)
    print(json.dumps(report))
