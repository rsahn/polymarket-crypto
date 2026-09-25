import pytest
from app.live.ctf_inventory_probe import scan_ctf


def test_archive_ten_block_windows_cover_range():
    class R:
        wallet='0x'+'1'*40
        log_window=10
        def __init__(self):self.ranges=[]
        def call(self,m,p):
            if m=='eth_chainId':return '0x89'
            if m=='eth_getBlockByNumber':return {'number':p[0],'hash':'0x'+'a'*64}
            if m=='eth_getCode':return '0x6000'
            assert m=='eth_getLogs'
            self.ranges.append((int(p[0]['fromBlock'],16),int(p[0]['toBlock'],16)))
            return []
    rpc=R()
    assert scan_ctf(rpc,100,124,set())['status']=='PASS_SCOPED_READS'
    assert rpc.ranges==[(100,109),(110,119),(120,124)]


def test_archive_factory_missing_has_no_default(monkeypatch):
    import analysis.qualify_genesis as q
    monkeypatch.delenv('POLYGON_ARCHIVE_RPC_URL',raising=False)
    with pytest.raises(q.DiscoveryBlocked):q.genesis_rpc('0x'+'1'*40,True)


def test_archive_factory_uses_explicit_endpoint(monkeypatch):
    import analysis.qualify_genesis as q
    monkeypatch.setenv('POLYGON_ARCHIVE_RPC_URL','https://example.com/secret-fixture')
    r=q.genesis_rpc('0x'+'1'*40,True)
    assert r.log_window==10 and r._endpoint=='https://example.com/secret-fixture'
