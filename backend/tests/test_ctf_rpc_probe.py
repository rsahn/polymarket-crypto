import pytest
from analysis import diagnose_ctf_rpc as q

@pytest.mark.parametrize('failure',[False,True])
def test_exactly_one_log_read_no_fallback(monkeypatch,failure):
    monkeypatch.setenv('POLYGON_ARCHIVE_RPC_URL','https://example.com/test')
    seen=[]
    class RPC:
        calls=[]
        def __init__(self,wallet,*,endpoint):self.wallet=wallet
        def call(self,m,p):
            seen.append((m,p))
            if m=='eth_chainId':return '0x89'
            assert m=='eth_getLogs'
            assert int(p[0]['fromBlock'],16)==94331195
            assert int(p[0]['toBlock'],16)==94331694
            if failure:raise RuntimeError('SECRET')
            return []
    monkeypatch.setattr(q,'PublicRPC',RPC)
    r=q.run()
    assert [x[0] for x in seen]==['eth_chainId','eth_getLogs']
    assert not r['credentials_loaded'] and not r['genesis_created']
    assert r['authenticated_get_attempts']==0
    assert 'SECRET' not in str(r)
    assert r['status']==('BLOCKED' if failure else 'TRANSPORT_READ_SUCCEEDED_ONLY')


def test_flags_block_before_rpc(monkeypatch):
    monkeypatch.setenv('REAL_ORDERS_ENABLED','true')
    def forbidden(*a):raise AssertionError()
    monkeypatch.setattr(q,'PublicRPC',forbidden)
    assert q.run()['rpc_calls']==[]
