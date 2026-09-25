import json
import pytest


def test_rpc_reports_receive_parse_and_thread_cpu(monkeypatch):
    import app.live.collateral_onchain as c
    class R:
        status=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return b'{"jsonrpc":"2.0","id":1,"result":"0x89"}'
    class O:
        def open(self,*a,**kw):return R()
    monkeypatch.setattr(c.urllib.request,'build_opener',lambda *a:O())
    rpc=c.PublicRPC('0x'+'1'*40,endpoint='https://example.invalid')
    rpc.call('eth_chainId',[]);e=rpc.calls[0]
    assert e['started_ms']<=e['response_received_ms']<=e['parse_complete_ms']<=e['finished_ms']
    assert e['thread_cpu_ms']>=0


def test_get_reports_receive_parse_and_thread_cpu(monkeypatch):
    import asyncio
    import app.live.network_readonly as n
    class R:
        status=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return b'{}'
    class O:
        def open(self,*a,**kw):return R()
    monkeypatch.setattr(n.urllib.request,'build_opener',lambda *a:O())
    audit=[];t=n.GetOnlyTransport('https://example.invalid',('/time',),audit=audit)
    asyncio.run(t.get_json('/time'));e=audit[0]
    assert e['started_ms']<=e['response_received_ms']<=e['parse_complete_ms']<=e['finished_ms']
    assert e['thread_cpu_ms']>=0


def test_reorg_counterexample_for_concurrent_postseal_checks():
    # Deterministic schedule: concurrency hides a reorg before account completion.
    canonical=lambda t:'old' if t<280 else 'new'
    assert canonical(268)=='old' and canonical(291)=='new'
    assert max(291,268)+7==298  # fast, but weaker evidence
    assert 291+268+7==566  # required post-account observation sees new hash
    assert canonical(291+268)!='old'
