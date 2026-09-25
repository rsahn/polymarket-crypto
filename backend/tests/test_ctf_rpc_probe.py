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
            if m=='eth_getCode':
                assert p==[q.CTF,hex(94331195)]
                return '0x6000'
            assert m=='eth_getLogs'
            assert int(p[0]['fromBlock'],16)==94331195
            assert int(p[0]['toBlock'],16)==94331204
            if failure:raise RuntimeError('SECRET')
            return []
    monkeypatch.setattr(q,'PublicRPC',RPC)
    r=q.run()
    assert [x[0] for x in seen]==['eth_chainId','eth_getCode','eth_getLogs']
    assert not r['credentials_loaded'] and not r['genesis_created']
    assert r['authenticated_get_attempts']==0
    assert 'SECRET' not in str(r)
    assert r['status']==('BLOCKED' if failure else 'PASS_READ_ONLY_RPC')


def test_flags_block_before_rpc(monkeypatch):
    monkeypatch.setenv('REAL_ORDERS_ENABLED','true')
    def forbidden(*a):raise AssertionError()
    monkeypatch.setattr(q,'PublicRPC',forbidden)
    assert q.run()['rpc_calls']==[]


@pytest.mark.parametrize('chain,code,reason',[
    ('0x1','0x6000','CHAIN_MISMATCH'),
    ('0x89','0x','HISTORICAL_CTF_CODE_UNAVAILABLE'),
    ('0x89','0x00','HISTORICAL_CTF_CODE_UNAVAILABLE')])
def test_wrong_chain_or_missing_history_blocks_logs(monkeypatch,chain,code,reason):
    monkeypatch.setenv('POLYGON_ARCHIVE_RPC_URL','https://example.com/test')
    seen=[]
    class R:
        calls=[]
        def __init__(self,*a,**kw):pass
        def call(self,m,p):
            seen.append(m)
            assert m!='eth_getLogs'
            return chain if m=='eth_chainId' else code
    monkeypatch.setattr(q,'PublicRPC',R)
    r=q.run()
    assert r['status']=='BLOCKED' and r['reason']==reason
    assert 'eth_getLogs' not in seen
