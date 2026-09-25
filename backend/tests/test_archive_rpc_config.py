import json
import pytest
from analysis import diagnose_ctf_rpc as q


def test_missing_archive_config_blocks_before_any_rpc(monkeypatch):
    monkeypatch.delenv('POLYGON_ARCHIVE_RPC_URL',raising=False)
    calls=[]
    def forbidden(*a,**kw):calls.append(True);raise AssertionError()
    monkeypatch.setattr(q,'PublicRPC',forbidden)
    r=q.run()
    assert r.get('reason')=='POLYGON_ARCHIVE_RPC_URL_NOT_CONFIGURED'
    assert calls==[] and r['rpc_calls']==[]

@pytest.mark.parametrize('url',['http://example.com/key','https://user:pass@example.com','https://example.com/#SECRET','https://example.com/\nSECRET'])
def test_invalid_endpoint_rejected_without_secret(url):
    from app.live.collateral_onchain import PublicRPC
    with pytest.raises(ValueError) as exc:PublicRPC('0x'+'1'*40,endpoint=url)
    assert 'SECRET' not in str(exc.value) and url not in str(exc.value)


def test_configured_endpoint_used_but_never_reported(monkeypatch):
    url='https://example.com/v2/SECRET_TEST_TOKEN'
    monkeypatch.setenv('POLYGON_ARCHIVE_RPC_URL',url)
    used=[]
    class R:
        calls=[]
        def __init__(self,wallet,*,endpoint):used.append(endpoint)
        def call(self,m,p):return '0x89' if m=='eth_chainId' else []
    monkeypatch.setattr(q,'PublicRPC',R)
    r=q.run()
    assert used==[url] and 'SECRET_TEST_TOKEN' not in json.dumps(r)
    assert r['rpc']=='CONFIGURED_POLYGON_ARCHIVE_RPC_URL'
