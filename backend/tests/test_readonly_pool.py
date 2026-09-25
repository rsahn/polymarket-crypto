import pytest

def test_persistent_pool_reuses_one_client_and_forbids_redirect_and_post():
    from app.live.readonly_pool import ReadOnlyPool
    import httpx
    calls=[]
    def handler(req):calls.append(req);return httpx.Response(200,content=b'{}')
    client=httpx.Client(transport=httpx.MockTransport(handler))
    pool=ReadOnlyPool(('https://example.invalid/time',),client=client)
    for _ in range(2):
        entry={};assert pool.read('GET','https://example.invalid/time',headers={},limit=100,timeout=1,entry=entry)==(200,b'{}')
    assert len(calls)==2 and pool.client is client
    with pytest.raises(ValueError):pool.read('POST','https://example.invalid/time',headers={},body=b'{}',limit=100,timeout=1,entry={})
    with pytest.raises(ValueError):pool.read('GET','https://else.invalid/time',headers={},limit=100,timeout=1,entry={})
    pool.close();assert client.is_closed


@pytest.mark.parametrize("mode", ["redirect", "timeout", "oversize"])
def test_pool_failure_redacted_without_retry(mode):
    import httpx
    from app.live.readonly_pool import ReadOnlyPool
    calls=[]
    def handler(req):
        calls.append(req)
        if mode=='timeout':raise httpx.ReadTimeout('FAKE_SECRET_SENTINEL',request=req)
        if mode=='redirect':return httpx.Response(302,headers={'location':'https://else.invalid/FAKE_SECRET_SENTINEL'})
        return httpx.Response(200,content=b'FAKE_SECRET_SENTINEL')
    pool=ReadOnlyPool(('https://example.invalid/time',),client=httpx.Client(transport=httpx.MockTransport(handler)))
    entry={}
    with pytest.raises(RuntimeError) as e:pool.read('GET','https://example.invalid/time',headers={},limit=2,timeout=1,entry=entry)
    assert len(calls)==1
    assert 'FAKE_SECRET_SENTINEL' not in str(e.value)+str(entry)
    pool.close()


def test_pool_rpc_transaction_forbidden_and_stream_reuse_observed():
    import httpx,json
    from app.live.readonly_pool import ReadOnlyPool
    stream=object();calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(200,content=b'{}',extensions={'network_stream':stream})
    pool=ReadOnlyPool(('https://example.invalid/rpc',),rpc=True,client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError):pool.read('POST','https://example.invalid/rpc',headers={},body=json.dumps({'method':'eth_sendRawTransaction'}).encode(),limit=100,timeout=1,entry={})
    assert not calls
    entries=[]
    for _ in range(2):
        entry={};pool.read('POST','https://example.invalid/rpc',headers={},body=b'{"method":"eth_chainId"}',limit=100,timeout=1,entry=entry);entries.append(entry)
    assert not entries[0]['connection_reuse_proven'] and entries[1]['connection_reuse_proven']
    pool.close()
