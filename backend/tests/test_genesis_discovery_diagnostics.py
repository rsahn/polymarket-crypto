import pytest
from app.live.genesis_discovery import conditional_snapshot

class RPC:
    wallet = 'public-fixture'
    def __init__(self): self.methods = []
    def call(self, method, params):
        self.methods.append(method)
        if method == 'eth_chainId': return '0x89'
        if method == 'eth_getBlockByNumber': return {'number': hex(100000), 'hash': '0x'+'a'*64, 'timestamp': '0x1'}
        if method == 'eth_getCode': return '0x6000' if int(params[1],16) >= 10 else '0x'
        raise AssertionError('No event scan expected')

def test_range_refusal_exposes_only_public_bounds():
    rpc = RPC()
    with pytest.raises(ValueError) as caught: conditional_snapshot(rpc, set())
    assert getattr(caught.value, 'reason', None) == 'CTF_RANGE_REQUIRES_REVIEWED_CHUNK_MANIFEST'
    assert caught.value.diagnostics == {'to_block':100000, 'block_hash':'0x'+'a'*64, 'from_block':10, 'block_count':99991, 'maximum_blocks':50000, 'logs_started':False}
    assert 'eth_getLogs' not in rpc.methods

def test_archive_error_is_redacted_and_identifies_stage():
    class Broken(RPC):
        def call(self, method, params):
            if method == 'eth_getCode': raise RuntimeError('SECRET_PROVIDER_PAYLOAD')
            return super().call(method, params)
    with pytest.raises(ValueError) as caught: conditional_snapshot(Broken(), set())
    assert caught.value.reason == 'CODE_BOUNDARY_READ_UNAVAILABLE'
    assert 'SECRET' not in str(caught.value)
    assert not caught.value.diagnostics['logs_started']

@pytest.mark.parametrize('broken',[False,True])
def test_collector_reports_discovery_failure_without_loading_l2(monkeypatch,broken):
    import asyncio,time
    import analysis.qualify_genesis as q
    monkeypatch.setattr(q,'qualification',lambda:({'collateral':{'observed_ms':1,'balance_human':'109.160000'},'inventory':{'remote_views':{'positions':{'observed_ms':1}}}},'a'*64))
    class R(RPC):
        calls=[]
        def __init__(self,*a):super().__init__()
        def call(self,m,p):
            if broken and m=='eth_getCode':raise RuntimeError('SECRET_PROVIDER_PAYLOAD')
            return super().call(m,p)
    class T:
        def __init__(self,*a,**kw):pass
        async def get_json(self,path):return int(time.time()) if path=='/time' else {'blocked':False}
    monkeypatch.setattr(q,'PublicRPC',R)
    monkeypatch.setattr(q,'GetOnlyTransport',T)
    monkeypatch.setattr(q,'read_local_ledger',lambda *a:({'configured':False},set()))
    touched=[]
    def forbidden(*a):touched.append(True);raise AssertionError('forbidden')
    monkeypatch.setattr(q,'load_existing',forbidden)
    monkeypatch.setattr(q,'create_genesis',forbidden)
    result=asyncio.run(q.run(True))
    expected='CODE_BOUNDARY_READ_UNAVAILABLE' if broken else 'CTF_RANGE_REQUIRES_REVIEWED_CHUNK_MANIFEST'
    assert result['genesis']['reasons']==[expected]
    assert result['genesis']['discovery']['logs_started'] is False
    assert not touched and not result['genesis']['created']
    import json
    assert 'SECRET_PROVIDER_PAYLOAD' not in json.dumps(result)
    assert len(result['readiness']['checks'])==12
