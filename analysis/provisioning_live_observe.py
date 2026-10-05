"""Bounded non-monetary observations; never issue production attestations."""
import asyncio
import concurrent.futures
import hashlib
import json
from pathlib import Path
import socket
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
from app.live.network_readonly import GetOnlyTransport


def ntp(host):
    """Unauthenticated diagnostic only; no claim of NTS or permanent clock safety."""
    result = {'host': host, 'authenticated': False}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(3)
            sock.connect((host, 123))
            packet = bytearray(48)
            packet[0] = 0x23
            t1 = time.time()
            mono = time.monotonic()
            stamp = int((t1 + 2208988800) * 2**32)
            packet[40:48] = stamp.to_bytes(8, 'big')
            sock.send(packet)
            raw = sock.recv(512)
            t4 = time.time()
            elapsed = time.monotonic() - mono
        if len(raw) < 48 or raw[0] & 7 != 4 or raw[0] >> 6 == 3 or not 1 <= raw[1] <= 15:
            raise ValueError('NTP_HEADER')
        if raw[24:32] != packet[40:48]:
            raise ValueError('NTP_ORIGIN')
        def stamp_at(i):
            return int.from_bytes(raw[i:i+8], 'big') / 2**32 - 2208988800
        t2, t3 = stamp_at(32), stamp_at(40)
        delay = (t4-t1)-(t3-t2)
        if delay < 0 or t3 < t2 or abs((t4-t1)-elapsed) > .002:
            raise ValueError('NTP_CAUSALITY_OR_CLOCK_STEP')
        root_delay = struct.unpack('!i', raw[4:8])[0] / 65536
        dispersion = int.from_bytes(raw[8:12], 'big') / 65536
        precision = 2 ** struct.unpack('b', raw[3:4])[0]
        offset = ((t2-t1)+(t3-t4))/2
        uncertainty = delay/2 + max(root_delay, 0)/2 + dispersion + precision + .002
        result.update(offset_ms=offset*1000, uncertainty_ms=uncertainty*1000,
            observed_ms=int(t4*1000), stratum=raw[1],
            numerical_bound_ms=(abs(offset)+uncertainty)*1000,
            diagnostic_within_100ms=(abs(offset)+uncertainty)<=.1)
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    return result


async def observe():
    from app.live.l2_existing_reader import load_existing, EXPECTED
    credentials, storage = load_existing(ROOT)
    wallet = sys.argv[2] if len(sys.argv) > 2 else '0x871d37b430c42ddbd0bbd37c29c02a2974109de9'
    if wallet.lower() not in {EXPECTED.lower(), '0x871d37b430c42ddbd0bbd37c29c02a2974109de9'}:
        raise ValueError('UNREVIEWED_WALLET')
    audit, results = [], {}
    public = GetOnlyTransport('https://data-api.polymarket.com', {'/positions'}, audit=audit)
    clob = None
    if credentials:
        from polymarket._internal.hmac import build_hmac_signature
        async def headers(path):
            ts = int(time.time())
            return {'POLY_ADDRESS': EXPECTED, 'POLY_API_KEY': credentials['apiKey'],
                'POLY_PASSPHRASE': credentials['passphrase'], 'POLY_TIMESTAMP': str(ts),
                'POLY_SIGNATURE': build_hmac_signature(secret=credentials['secret'],
                    timestamp=ts, method='GET', path=path, body=None)}
        clob = GetOnlyTransport('https://clob.polymarket.com',
            {'/balance-allowance', '/data/orders', '/data/trades'}, headers=headers, audit=audit)
    async def read(name, transport, path, params):
        if transport is None:
            results[name] = {'status': 'CREDENTIALS_UNAVAILABLE'}
            return
        try:
            pages, count, seen, exhausted = [], 0, set(), False
            for page in range(20):
                raw = await transport.get_json(path, params=params)
                pages.append(hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest())
                if name == 'cash':
                    from decimal import Decimal
                    value = Decimal(str(raw['balance']))
                    if not value.is_finite() or value < 0 or not isinstance(raw['allowances'], dict):
                        raise ValueError('CASH_SCHEMA')
                    break
                rows = raw if isinstance(raw, list) else raw['data']
                if not isinstance(rows, list):
                    raise ValueError('PAGE_SCHEMA')
                count += len(rows)
                if name == 'positions':
                    if len(rows) < 500:
                        exhausted = True
                        break
                    params = {**params, 'offset': (page+1)*500}
                else:
                    cursor = raw['next_cursor']
                    if cursor in ('LTE=', '', None):
                        exhausted = True
                        break
                    if not isinstance(cursor, str) or cursor in seen:
                        raise ValueError('REPEATED_CURSOR')
                    seen.add(cursor)
                    params = {**params, 'next_cursor': cursor}
            results[name] = {'status': 'OBSERVED_ONLY', 'pages_sha256': pages,
                'count': count if name != 'cash' else None,
                'pagination_exhausted': exhausted if name != 'cash' else None,
                'wallet_completeness_proven': False,
                'scope': 'requested wallet/credential view; cross-credential coverage unproven'}
        except Exception as exc:
            results[name] = {'status': 'FAILED', 'error_type': type(exc).__name__}
    await asyncio.gather(
        read('cash', clob, '/balance-allowance', {'asset_type': 'COLLATERAL', 'signature_type': 0 if wallet.lower()==EXPECTED.lower() else 3}),
        read('orders', clob, '/data/orders', {}),
        # Entire authenticated credential view; a maker filter can hide taker fills.
        read('trades', clob, '/data/trades', {}),
        read('positions', public, '/positions', {'user': wallet, 'sizeThreshold': 0, 'limit': 500, 'offset': 0}))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        clock = list(pool.map(ntp, ('time.cloudflare.com', 'time.google.com', 'time.windows.com')))
    return {'observed_ms': time.time_ns()//1000000, 'candidate_wallet': wallet,
        'candidate_signer': EXPECTED, 'identity_origin': 'existing repository configuration; not approval',
        'credential_storage': storage, 'reads': results, 'network_audit': audit,
        'clock_samples': clock, 'CLOCK_100MS_QUALIFIED': False,
        'clock_limit': 'Unauthenticated UDP samples; no continuous validity or independently pinned time authority.',
        'LIVE_GATE': 'BLOCKED', 'submit_allowed': False, 'raw_account_payloads_logged': False}


if __name__ == '__main__':
    result = asyncio.run(observe())
    with Path(sys.argv[1]).open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps({'reads': result['reads'], 'clock_samples': result['clock_samples']}))
