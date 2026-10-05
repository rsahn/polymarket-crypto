import copy
import pytest
from eth_keys import keys
from analysis.authority_windows.finalize_policy import proposal


def public():
    # Test scalar only; no production key or account provisioned.
    point=keys.PrivateKey(bytes.fromhex('01'*32)).public_key
    return dict(authority_sid='S-1-5-21-1-2-3-1005',supervisor_sid='S-1-5-21-1-2-3-1002',
                public_key='0x04'+point.to_bytes().hex(),dpapi_roundtrip=True,
                wallet_secret_access_denied=True,approved=False,key_version='v1')


def test_only_two_kinds_and_no_implicit_approval():
    p=public(); result=proposal(p,p['authority_sid'],'session')
    assert result['approved'] is False
    assert result['source_trust_approved'] is False
    assert result['policy']['keys']['d6-windows-telemetry-v1']['kinds']==['clock_sanity','ws_healthy']
    assert result['policy']['keys']['d6-windows-telemetry-v1']['address']==keys.PrivateKey(bytes.fromhex('01'*32)).public_key.to_checksum_address()


@pytest.mark.parametrize('field,value',[('authority_sid','S-1-5-21-1-2-3-1002'),('approved',True),('dpapi_roundtrip',False),('wallet_secret_access_denied',False)])
def test_unproven_or_same_principal_rejected(field,value):
    p=public(); p[field]=value
    with pytest.raises(ValueError):proposal(p,'S-1-5-21-1-2-3-1005','session')


def test_rotation_changes_digest_and_rejects_old_signature():
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from analysis.d6.real_execution_calibration_v1.core import encoded
    from analysis.d6.real_execution_calibration_v1.production_authority import ProductionAuthority
    p=public(); old=proposal(p,p['authority_sid'],'session')
    altered=copy.deepcopy(p); altered['key_version']='v2'
    altered['public_key']='0x04'+keys.PrivateKey(bytes.fromhex('02'*32)).public_key.to_bytes().hex()
    new=proposal(altered,p['authority_sid'],'session')
    assert old['policy_digest']!=new['policy_digest']
    r=dict(old['policy']['context'],kind='clock_sanity',key_id='d6-windows-telemetry-v1',provider=old['policy']['provider'],trust_policy_digest=old['policy_digest'],observed_ms=1,valid_until_ms=2)
    r['provenance_signature']=Account.from_key(bytes.fromhex('01'*32)).sign_message(encode_defunct(text='D6_PROVENANCE_V1:'+encoded(r))).signature.hex()
    authority=ProductionAuthority(**new['policy'],clock=lambda:1,approval_digest=new['policy_digest'])
    assert authority.verify(r) is False
