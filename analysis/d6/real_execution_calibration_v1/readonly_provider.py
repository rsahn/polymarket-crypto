"""Concrete local read-only composition, NOT an independent evidence authority.
No credential loader, SDK constructor, signing method or approval/write route.
Constructors only inspect public identities. Reads run solely on explicit request.
"""
from dataclasses import dataclass,field
from importlib.metadata import version
import re
from .adapters import AccountAdapter


def address(value):
    if type(value) is not str or not re.fullmatch(r'0x[0-9a-fA-F]{40}',value):raise ValueError('PUBLIC_ADDRESS_REQUIRED')
    return value.lower()

@dataclass(frozen=True)
class SDKIdentityBinding:
    client:object=field(repr=False,compare=False)
    wallet:str
    signer:str
    environment:str
    sdk_version:str='0.11.0'
    @classmethod
    def inspect(cls,client,*,wallet,signer,environment='production'):
        from polymarket import AsyncSecureClient
        from app.live.network_readonly import ReadOnlyClient
        if version('polymarket-client')!='0.11.0':raise ValueError('SDK_CLASS_OR_VERSION')
        if type(client) is AsyncSecureClient:
            # Only documented public properties; never client.credentials or signer.key.
            from polymarket.environments import PRODUCTION
            if address(str(client.wallet))!=address(wallet) or address(str(client.signer))!=address(signer) or environment!='production' or client.environment is not PRODUCTION:raise ValueError('SDK_PUBLIC_IDENTITY')
        elif type(client) is ReadOnlyClient:
            # ReadOnlyClient has no signer or environment; bind wallet only.
            if address(str(client.wallet))!=address(wallet):raise ValueError('SDK_PUBLIC_IDENTITY')
        else:
            raise ValueError('SDK_CLASS_OR_VERSION')
        return cls(client,address(wallet),address(signer),environment)
    def matches(self,client):
        if client is not self.client:return False
        try:return self.inspect(client,wallet=self.wallet,signer=self.signer,environment=self.environment)==self
        except (ValueError,AttributeError,RuntimeError):return False
    def report(self):
        return dict(status='LOCAL_PUBLIC_IDENTITY_BOUND_ONLY',sdk_version=self.sdk_version,wallet=self.wallet,signer=self.signer,environment=self.environment,independent_attestation=False,transport_qualified=False,submit_allowed=False)

class RepositoryReadOnlyProvider:
    """Existing GET-only facade + credential/enumerated-asset readers.
    Never promotes pagination completion to full-wallet/finality/fee proof.
    Expose account_reader/position_reader to PreparedSession, or snapshot() for
    a preparation observation. Not usable as qualified evidence_source.
    """
    def __init__(self,client,*,wallet,spender,collateral,asset_types,session,clock):
        from app.live.network_readonly import ReadOnlyClient,GetOnlyTransport
        from app.live.production_readonly import AccountStateSource,PositionSource
        if type(client) is not ReadOnlyClient or version('polymarket-client')!='0.11.0':raise ValueError('READONLY_CLIENT_REQUIRED')
        if address(str(client.wallet))!=address(wallet):raise ValueError('READONLY_WALLET')
        address(spender)
        for transport,base in ((client.clob,'https://clob.polymarket.com'),(client.data,'https://data-api.polymarket.com')):
            if type(transport) is not GetOnlyTransport or transport.base!=base:raise ValueError('GET_ONLY_OFFICIAL_ENDPOINT_REQUIRED')
        if collateral not in ('pUSD','USDC'):raise ValueError('COLLATERAL_UNREVIEWED')
        self.client=client;self._bindings=(client,client.clob,client.data,str(client.wallet),client.signature_type,client.clob.base,client.data.base,client.clob.routes,client.data.routes)
        self.account_reader=AccountStateSource(client,wallet=wallet,spender=spender,clock=clock,collateral_symbol=collateral)
        self.position_reader=PositionSource(client,wallet=wallet,asset_types=asset_types,clock=clock,collateral_symbol=collateral)
        self.adapter=AccountAdapter(self.account_reader,self.position_reader,account=wallet,collateral=collateral,session=session,clock=clock)
    def check_binding(self):
        c=self.client;old=self._bindings
        if any(a is not b for a,b in zip((c,c.clob,c.data),old[:3])) or (str(c.wallet),c.signature_type,c.clob.base,c.data.base,c.clob.routes,c.data.routes)!=old[3:]:raise ValueError('READONLY_BINDING_CHANGED')
        if self.account_reader.client is not c or self.position_reader.client is not c:raise ValueError('READONLY_READER_REPLACED')
    async def snapshot(self):
        self.check_binding();result=await self.adapter.snapshot();self.check_binding()
        result.update(scope='CREDENTIAL_AND_ENUMERATED_ASSETS_ONLY',atomic_frontier=None,finality_proven=False,fee_effects_proven=False,independent_attestation=False,submit_allowed=False)
        return result
    async def execution(self,order_id):raise ValueError('FINAL_FEES_AND_FULL_WALLET_AUTHORITY_NOT_IMPLEMENTED')
