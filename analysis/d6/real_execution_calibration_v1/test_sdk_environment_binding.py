"""Actual pinned SDK environment; no network, real credentials or order signing."""
import asyncio
from types import SimpleNamespace
import pytest
from eth_account import Account
from polymarket.clients.async_secure import AsyncSecureClient, PRODUCTION, get_environment_config
from polymarket.models.clob.api_key import ApiKeyCreds
from .readonly_provider import SDKIdentityBinding


def test_real_sdk_production_environment_and_replacement_rejected():
    async def case():
        signer = Account.create()
        client = AsyncSecureClient._construct_for_wallet(signer=signer, wallet=signer.address,
            wallet_type='EOA', signer_type='OWNER', environment=PRODUCTION,
            config=get_environment_config(PRODUCTION),
            credentials=ApiKeyCreds(apiKey='test', secret='dGVzdA==', passphrase='test'),
            api_key=None, logger=None, on_rate_limit_update=None)
        try:
            binding = SDKIdentityBinding.inspect(client, wallet=signer.address, signer=signer.address)
            assert binding.matches(client)
            original_context = client._ctx
            for false_environment in ('production', SimpleNamespace(name='production'), None):
                client._ctx = SimpleNamespace(wallet=original_context.wallet,
                    signer=original_context.signer, environment=false_environment)
                assert not binding.matches(client)
                with pytest.raises(ValueError, match='SDK_PUBLIC_IDENTITY'):
                    SDKIdentityBinding.inspect(client, wallet=signer.address, signer=signer.address)
            client._ctx = original_context
            assert binding.matches(client)
            with pytest.raises(ValueError, match='SDK_PUBLIC_IDENTITY'):
                SDKIdentityBinding.inspect(client, wallet=signer.address, signer=signer.address, environment='test')
        finally:
            if 'original_context' in locals():
                client._ctx = original_context
            await client.close()
    asyncio.run(case())
