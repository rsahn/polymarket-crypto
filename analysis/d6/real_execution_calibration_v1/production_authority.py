"""Externally pinned secp256k1 provenance; no embedded signing keys or trust defaults."""
import copy
from types import MappingProxyType
from eth_account import Account
from eth_account.messages import encode_defunct
from .core import encoded
from .preflight import REQUIRED

class ProductionAuthority:
    def __init__(self, *, keys, provider, context, clock, approval_digest):
        from .schemas import hash256
        hash256(approval_digest)
        if not keys or not provider: raise ValueError('EXTERNAL_TRUST_POLICY_REQUIRED')
        self.keys=MappingProxyType({k:(v['address'].lower(),frozenset(v['kinds'])) for k,v in keys.items()})
        self.provider=provider; self.context=MappingProxyType(dict(context)); self.clock=clock
        self.approval_digest=approval_digest; self.bindings=None; self.client=None; self.identity=None

    def verify_provenance(self, record):
        """Authenticate before classifying an expired feed as an outage."""
        try:
            r=copy.deepcopy(record);signature=bytes.fromhex(r.pop('provenance_signature'))
            key,kinds=self.keys[r['key_id']]
            if 'check' in r and r.get('kind',r['check'])!=r['check']:return False
            if r.get('provider')!=self.provider or r.get('kind',r.get('check')) not in kinds:return False
            if any(r.get(k)!=v for k,v in self.context.items()):return False
            if r.get('trust_policy_digest')!=self.approval_digest:return False
            return Account.recover_message(encode_defunct(text='D6_PROVENANCE_V1:'+encoded(r)),signature=signature).lower()==key
        except Exception:return False

    def verify(self, record):
        try:
            if not self.verify_provenance(record):return False
            now=self.clock();r=record
            if type(r['observed_ms']) is not int or type(r['valid_until_ms']) is not int:return False
            lifetime=259200000 if r.get('kind')=='baseline' else 5000
            return 0<=now-r['observed_ms']<=lifetime and now<=r['valid_until_ms']<=r['observed_ms']+lifetime
        except Exception:return False

    def bind(self, *, client, source, custody):
        from .readonly_provider import SDKIdentityBinding
        from .production_evidence_source import ProductionEvidenceSource
        if self.bindings is not None: raise ValueError('AUTHORITY_ALREADY_BOUND')
        if type(source) is not ProductionEvidenceSource or source.authority is not self: raise ValueError('SOURCE_BINDING')
        self.identity=SDKIdentityBinding.inspect(client,wallet=self.context['account'],signer=self.context['signer'])
        self.client=client
        self.bindings=(self,custody.channel,custody.verifier.authority,source,self)

    def verify_client(self, client, proof):
        return self.verify(proof) and client is self.client and self.identity is not None and self.identity.matches(client)

    def verify_bindings(self, bindings, proof):
        return (self.bindings is not None and type(bindings) is tuple and len(bindings)==5
                and all(a is b for a,b in zip(bindings,self.bindings))
                and type(proof) is dict and all(self.verify(proof.get(k)) for k in REQUIRED))
