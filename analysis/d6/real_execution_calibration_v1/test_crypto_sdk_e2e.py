"""Real SDK cryptography with ephemeral fixture keys; only submit is replaced.
Metadata is explicitly seeded in the SDK cache. Network is denied by the suite.
"""
import asyncio
from dataclasses import replace
from decimal import Decimal
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from polymarket.clients.async_secure import AsyncSecureClient, get_environment_config, PRODUCTION
from polymarket.models.clob.api_key import ApiKeyCreds
from polymarket._internal.actions.orders.market_data import MarketInfo, PlatformFeeInfo
from polymarket._internal.actions.orders.context import resolve_order_exchange_address
from polymarket._internal.actions.orders.types import UnsignedOrder
from polymarket._internal.actions.orders.typed_data import build_order_typed_data,build_order_signature
from .test_runtime_qualification import fixture,drive
from .transport import SDKPort

@pytest.mark.parametrize('token',['1','1099511627776'])
@pytest.mark.parametrize('mode',['full','partial','none'])
@pytest.mark.parametrize('wallet_type',['EOA','DEPOSIT_WALLET'])
def test_real_sdk_btc_sign_submit_fill_exit(tmp_path,monkeypatch,mode,wallet_type,token):
    async def case():
        signer=Account.create();wallet=signer.address if wallet_type=='EOA' else '0x'+'12'*20
        client=AsyncSecureClient._construct_for_wallet(signer=signer,wallet=wallet,wallet_type=wallet_type,signer_type='OWNER',environment=PRODUCTION,config=get_environment_config(PRODUCTION),credentials=ApiKeyCreds(apiKey='fixture',secret='Zml4dHVyZQ==',passphrase='fixture'),api_key=None,logger=None,on_rate_limit_update=None)
        meta=client._ctx.order_metadata
        meta._conditions.set(token,'0x'+'34'*32)
        meta._markets.set('0x'+'34'*32,MarketInfo(PlatformFeeInfo(Decimal(0),Decimal(1)),False,Decimal('.01'),frozenset((token,str(int(token)+1)))))
        c,l,now,log,calls=fixture(tmp_path,mode,token=token,down=str(int(token)+1),maker=wallet,signer_address=signer.address)
        c.port=SDKPort(client,maker=wallet,signer=signer.address,ledger=l,arm=c.arm,qualified=True)
        submitted=[]
        async def post(path,*,json):
            assert path=='/order'
            cid=next(cid for cid,o in l.orders.items() if o['order_id'] is None)
            # SDK's full request codec is exercised, including real signature.
            o=json['order'];sig=bytes.fromhex(o['signature'][2:]);assert len(sig)>=65
            unsigned=UnsignedOrder(chain_id=client._ctx.environment_config.chain_id,exchange_address=resolve_order_exchange_address(client._ctx.environment_config,asset_id=token,neg_risk=False),expiration=0,builder=o['builder'],maker=o['maker'],maker_amount=int(o['makerAmount']),metadata=o['metadata'],order_type='FAK',salt=int(o['salt']),side=o['side'],signature_type=int(o['signatureType']),signer=o['signer'],taker_amount=int(o['takerAmount']),timestamp=int(o['timestamp']),token_id=o['tokenId'],protocol_version='3' if token=='1' else '2')
            recovered=Account.recover_message(encode_typed_data(full_message=build_order_typed_data(unsigned)),signature=sig[:65])
            assert recovered==signer.address
            assert build_order_signature(unsigned,'0x'+sig[:65].hex())==o['signature']
            if wallet_type=='DEPOSIT_WALLET':
                from .transport import verify_deposit_signature
                from polymarket._internal.actions.orders.orders import create_signed_order
                signed=create_signed_order(unsigned,o['signature'])
                assert verify_deposit_signature(signed,signer.address)
                assert not verify_deposit_signature(signed,'0x'+'01'*20)
                assert not verify_deposit_signature(replace(signed,taker_amount=signed.taker_amount+1),signer.address)
                assert not verify_deposit_signature(replace(signed,signature=signed.signature[:-2]+'ff'),signer.address)
            submitted.append(cid)
            return dict(success=True,errorMsg='',orderID=cid+'-remote',status='matched',makingAmount='0',takingAmount='0',tradeIDs=[],transactionsHashes=[])
        monkeypatch.setattr(client._ctx.secure_clob,'post_json',post)
        try:
            await drive(c,now)
            if c.v1['failures']:raise c.v1['failures'][0]
            assert l.reconciled and not l.stop and not any(l.positions.values())
            assert len(submitted)==(1 if mode=='none' else 2)
            assert l.cash==Decimal({'full':'499.3','partial':'499.7','none':'500'}[mode])
            assert l.attempts==1 and l.allocated==26
        finally:l.journal.close();await client.close()
    asyncio.run(case())
