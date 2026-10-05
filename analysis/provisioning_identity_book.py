"""Inspect a real SDK instance locally, then observe a public real StreamBook.
No create/bootstrap/deployment/order method is called; no production arm exists.
"""
import asyncio
from contextlib import suppress
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
PRODUCTION_DEPOSIT_WALLET = '0x871d37B430C42DDBD0BBD37C29c02A2974109DE9'


def diagnostic_json(value):
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    raise TypeError('UNSUPPORTED_DIAGNOSTIC_TYPE')


async def identity():
    from importlib.metadata import version
    from eth_account import Account
    from polymarket import AsyncSecureClient
    from polymarket.clients.async_secure import PRODUCTION, get_environment_config, classify_account
    from polymarket.models.clob.api_key import ApiKeyCreds
    from app.live.l2_existing_reader import load_existing, EXPECTED
    from analysis.d6.real_execution_calibration_v1.readonly_provider import SDKIdentityBinding
    client = None
    stage = 'version'
    try:
        if version('polymarket-client') != '0.11.0':
            raise ValueError('SDK_VERSION')
        stage = 'existing_credentials'
        credentials, status = load_existing(ROOT)
        if not credentials:
            raise ValueError('CREDENTIALS')
        stage = 'local_identity_config'
        selected = {}
        for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.strip().partition('=')
            if sep and name in ('SIGNER_PRIVATE_KEY', 'POLYMARKET_WALLET_ADDRESS',
                                'REAL_ORDERS_ENABLED', 'LIVE_EXECUTION_ARMED'):
                if name in selected:
                    raise ValueError('DUPLICATE_CONFIG')
                selected[name] = value.strip().strip('"').strip("'")
        stage = 'local_execution_flags'
        if any(selected.get(k, 'false').lower() != 'false' for k in ('REAL_ORDERS_ENABLED', 'LIVE_EXECUTION_ARMED')):
            raise ValueError('FLAGS')
        stage = 'derive_public_signer'
        signer = Account.from_key(selected.pop('SIGNER_PRIVATE_KEY'))
        configured_wallet = selected['POLYMARKET_WALLET_ADDRESS']
        # Explicit user-authorized diagnostic composition. Never edit .env.
        wallet = PRODUCTION_DEPOSIT_WALLET
        if signer.address.lower() != EXPECTED.lower():
            raise ValueError('SIGNER')
        stage = 'classify_wallet'
        config = get_environment_config(PRODUCTION)
        account = classify_account(signer=signer.address, wallet=wallet, config=config.wallet_derivation)
        if account.wallet_type != 'DEPOSIT_WALLET' or account.signer_type != 'OWNER':
            raise ValueError('PRODUCTION_DEPOSIT_OWNER_REQUIRED')
        # Pinned local construction only; public create can deploy a wallet or
        # create credentials and is deliberately not called for this diagnostic.
        stage = 'sdk_local_construction'
        client = AsyncSecureClient._construct_for_wallet(signer=signer, wallet=wallet,
            wallet_type='DEPOSIT_WALLET', signer_type='OWNER',
            environment=PRODUCTION, config=config, credentials=ApiKeyCreds(**credentials),
            api_key=None, logger=None, on_rate_limit_update=None)
        stage = 'sdk_identity_binding'
        binding = SDKIdentityBinding.inspect(client, wallet=wallet, signer=signer.address)
        return {'status': 'REAL_SDK_LOCAL_IDENTITY_VERIFIED', **binding.report(),
            'wallet_type': account.wallet_type, 'production_authority_bound': False,
            'configured_wallet': configured_wallet, 'active_environment_modified': False,
            'explicit_production_composition': True, 'sdk_identity_binding_qualified': binding.matches(client),
            'wallet_deployment_checked': False, 'credential_network_bootstrap': False}
    except Exception as exc:
        return {'status': 'FAILED', 'stage': stage, 'error_type': type(exc).__name__}
    finally:
        if client:
            await client.close()


async def book():
    from app.live.network_readonly import GetOnlyTransport
    from app.live.readonly_book_stream import StreamBook
    task = None
    try:
        slug = 'btc-updown-5m-' + str(int(time.time()) // 300 * 300)
        transport = GetOnlyTransport('https://gamma-api.polymarket.com', {'/markets'})
        markets = await transport.get_json('/markets', {'slug': slug})
        if len(markets) != 1 or markets[0]['slug'] != slug:
            raise ValueError('MARKET_NOT_UNIQUE')
        m = markets[0]
        tokens = json.loads(m['clobTokenIds']) if isinstance(m['clobTokenIds'], str) else m['clobTokenIds']
        outcomes = json.loads(m['outcomes']) if isinstance(m['outcomes'], str) else m['outcomes']
        if len(tokens) != 2 or [x.lower() for x in outcomes] != ['up', 'down']:
            raise ValueError('OUTCOME_MAPPING')
        expiry = int(datetime.fromisoformat(m['endDate'].replace('Z', '+00:00')).timestamp()*1000)
        stream = StreamBook(slug, m['conditionId'], tokens, expiry)
        task = asyncio.create_task(stream.run(reconnect=False))
        last = {}
        for _ in range(150):
            await asyncio.sleep(.1)
            last = stream.read()
            if last.get('available') or task.done():
                break
        return {'slug': slug, 'condition_id': m['conditionId'], 'tokens': tokens,
            'observed_ms': time.time_ns()//1000000, 'available': last.get('available', False),
            'book_synced': last.get('book_synced', False), 'messages': stream.messages,
            'book_state': last,
            'failure': stream.failure, 'production_session_bound': False,
            'regression_diagnostics': stream.diagnostics.get('regression_event'),
            'freshness_diagnostics': {k:stream.diagnostics.get(k) for k in
                ('source_age_at_receipt_ms','local_processing_ms','rejected_message_age_ms',
                 'freshness_cause','parser_reason','exception_category')},
            'diagnostic_only': True, 'expiry_ms': expiry}
    except Exception as exc:
        return {'available': False, 'error_type': type(exc).__name__}
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, 5)


async def main():
    sdk = await identity()
    stream = await book()
    result = {'sdk_identity': sdk, 'real_streambook': stream, 'LIVE_GATE': 'BLOCKED', 'armed': False}
    encoded = json.dumps(result, indent=2, default=diagnostic_json, allow_nan=False)
    with Path(sys.argv[1]).open('x', encoding='utf-8') as f:
        f.write(encoded)
    print(encoded)


if __name__ == '__main__':
    asyncio.run(main())
