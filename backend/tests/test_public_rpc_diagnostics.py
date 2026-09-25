import json
import urllib.error
import pytest
from app.live.collateral_onchain import PublicRPC,CTF

WALLET='0x'+'1'*40

def install(monkeypatch,payload=None,error=None):
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return json.dumps(payload).encode()
    class Opener:
        def open(self,*args,**kwargs):
            if error:raise error
            return Response()
    monkeypatch.setattr('urllib.request.build_opener',lambda *args:Opener())

@pytest.mark.parametrize('code,message,category',[
    (-32601,'eth_getLogs method not found SECRET','METHOD_UNAVAILABLE'),
    (-32005,'block range limit SECRET','RANGE_LIMIT'),
    (-32000,'upgrade your plan SECRET','PLAN_RESTRICTION'),
    (-32000,'opaque SECRET','UNCLASSIFIED_RPC_ERROR')])
def test_rpc_error_retains_only_code_and_category(monkeypatch,code,message,category):
    install(monkeypatch,{'jsonrpc':'2.0','id':1,'error':{'code':code,'message':message,'data':'SECRET'}})
    rpc=PublicRPC(WALLET)
    with pytest.raises(RuntimeError) as error:rpc.call('eth_chainId',[])
    entry=rpc.calls[-1]
    assert entry.get('http_status')==200
    assert entry.get('rpc_error_code')==code
    assert entry.get('error_category')==category
    assert 'SECRET' not in json.dumps(entry)+str(error.value)

@pytest.mark.parametrize('error,category,status',[
    (urllib.error.HTTPError('https://secret.invalid',403,'SECRET',{},None),'HTTP_ERROR',403),
    (TimeoutError('SECRET'),'TIMEOUT',None)])
def test_transport_error_redacted(monkeypatch,error,category,status):
    install(monkeypatch,error=error)
    rpc=PublicRPC(WALLET)
    with pytest.raises(RuntimeError) as caught:rpc.call('eth_chainId',[])
    assert rpc.calls[-1].get('error_category')==category
    assert rpc.calls[-1].get('http_status')==status
    assert 'SECRET' not in json.dumps(rpc.calls)+str(caught.value)

def test_getlogs_failure_records_bounds_without_wallet_topics(monkeypatch):
    from eth_utils import keccak
    signatures=['0x'+keccak(text=x).hex() for x in ('TransferSingle(address,address,address,uint256,uint256)','TransferBatch(address,address,address,uint256[],uint256[])')]
    install(monkeypatch,{'jsonrpc':'2.0','id':1,'error':{'code':-32000,'message':'opaque SECRET'}})
    rpc=PublicRPC(WALLET)
    with pytest.raises(RuntimeError):
        rpc.call('eth_getLogs',[{'address':CTF,'fromBlock':hex(94331195),'toBlock':hex(94331694),'topics':[signatures,None,None,'0x'+WALLET[2:].rjust(64,'0')]}])
    entry=rpc.calls[-1]
    assert entry['from_block']==94331195 and entry['to_block']==94331694
    assert entry['rpc_error_code']==-32000 and entry['http_status']==200
    assert WALLET not in json.dumps(entry) and 'topics' not in entry

def test_mismatched_response_id_never_trusts_error(monkeypatch):
    install(monkeypatch,{'jsonrpc':'2.0','id':900,'error':{'code':-32601,'message':'SECRET'}})
    rpc=PublicRPC(WALLET)
    with pytest.raises(RuntimeError):rpc.call('eth_chainId',[])
    assert rpc.calls[-1]['error_category']=='RPC_ENVELOPE_INVALID'
    assert 'rpc_error_code' not in rpc.calls[-1]
