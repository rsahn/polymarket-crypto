"""Pinned SDK RPC, read-only method allowlist. No transaction submission API."""
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request
from polymarket.clients.async_secure import PRODUCTION, get_environment_config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def main():
    config = get_environment_config(PRODUCTION)
    endpoint = sys.argv[2] if len(sys.argv)>2 else config.rpc_url
    if endpoint not in {config.rpc_url, 'https://polygon-bor-rpc.publicnode.com'}:
        raise ValueError('UNREVIEWED_RPC')
    sequence = 0
    def read(method, params):
        nonlocal sequence
        if method not in {'eth_chainId', 'eth_getBlockByNumber', 'eth_getCode', 'eth_call'}:
            raise ValueError('READ_ONLY_METHOD_REQUIRED')
        sequence += 1
        payload = {'jsonrpc': '2.0', 'id': sequence, 'method': method, 'params': params}
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}, method='POST')
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(1000001)
        if len(raw) > 1000000: raise ValueError('SIZE')
        result = json.loads(raw)
        if result.get('id') != sequence or 'error' in result: raise ValueError('RPC_RESPONSE')
        return result['result']
    report = {'rpc': endpoint, 'configured_collateral_contract': config.collateral_token,
              'wallet_completeness_proven': False, 'submit_allowed': False}
    try:
        chain = int(read('eth_chainId', []), 16)
        if chain != 137: raise ValueError('CHAIN')
        block = read('eth_getBlockByNumber', ['finalized', False])
        height = block['number']
        report.update(chain_id=chain, finalized_block=height, finalized_hash=block['hash'],
                      block_timestamp=int(block['timestamp'],16), observed_ms=time.time_ns()//1000000)
        observations = []
        for wallet in ('0x9348efd557a09e644795c8f114bcf0bef86f203a','0x871d37b430c42ddbd0bbd37c29c02a2974109de9'):
            code = read('eth_getCode', [wallet, height])
            balance = read('eth_call', [{'to': config.collateral_token,
                'data': '0x70a08231'+wallet[2:].rjust(64,'0')}, height])
            owner = None
            if code != '0x':
                try:
                    raw_owner = read('eth_call', [{'to': wallet, 'data': '0x8da5cb5b'}, height])
                    if len(raw_owner)==66:
                        owner='0x'+raw_owner[-40:]
                except Exception:
                    pass
            observations.append({'wallet': wallet, 'code_present': code != '0x',
                'owner_at_finalized_block': owner,
                'code_sha256': hashlib.sha256(code.encode()).hexdigest(),
                'collateral_balance_raw': str(int(balance,16))})
        report['observations'] = observations
        report['status'] = 'SINGLE_RPC_FINALIZED_OBSERVATIONS_ONLY'
    except Exception as exc:
        report.update(status='FAILED', error_type=type(exc).__name__, http_status=getattr(exc,'code',None))
    with Path(sys.argv[1]).open('x', encoding='utf-8') as f:
        json.dump(report,f,indent=2)
    print(json.dumps(report))


if __name__ == '__main__': main()
