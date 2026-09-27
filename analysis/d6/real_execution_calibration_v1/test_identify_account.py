import copy,json,time,types
import pytest
from .identify_account import PinnedCashRPC,read_cash,assess,abi_text,EOA,D6,CONTRACT,BALANCES

def text_abi(s):
    b=s.encode();return '0x'+(32).to_bytes(32,'big').hex()+len(b).to_bytes(32,'big').hex()+(b+b'\x00'*((-len(b))%32)).hex()
def word(n):return '0x'+format(n,'064x')

class Provider:
    def __init__(self,change=None):self.calls=[];self.change=change;self.header={'number':'0x123','timestamp':hex(int(time.time())),'hash':'0x'+'a'*64}
    def open(self,req,timeout):
        assert req.get_method()=='POST'
        p=json.loads(req.data);self.calls.append(p);method=p['method'];params=p['params']
        if method=='eth_chainId':result='0x89' if self.change!='chain' else '0x1'
        elif method=='eth_getBlockByNumber':
            result=dict(self.header)
            if self.change=='stale':result['timestamp']=hex(int(time.time())-200)
            if self.change=='reorg' and params[0]!='latest':result['hash']='0x'+'b'*64
        elif method=='eth_call':
            assert params[1]=='0x123' and params[0]['to']==CONTRACT
            data=params[0]['data']
            result={'0x95d89b41':text_abi('pUSD' if self.change!='symbol' else 'BAD'),'0x313ce567':word(6 if self.change!='decimals' else 18),'0x06fdde03':text_abi('Polymarket USD')}.get(data)
            if result is None:result=word(109160000 if BALANCES[data]==D6 else 0)
        else:raise AssertionError('FORBIDDEN_RPC_REACHED_WIRE')
        body=json.dumps({'jsonrpc':'2.0','id':p['id'],'result':result}).encode()
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return body
        return Response()

def run(monkeypatch,change=None):
    provider=Provider(change)
    monkeypatch.setattr('urllib.request.build_opener',lambda *a:provider)
    monkeypatch.setattr('analysis.d6.real_execution_calibration_v1.identify_account.time.sleep',lambda *a:None)
    rpc=PinnedCashRPC();return read_cash(rpc),provider

def test_same_block_metadata_both_addresses_and_recheck(monkeypatch):
    r,p=run(monkeypatch)
    assert r['status']=='PINNED_CASH_OBSERVED' and r['balances_raw']=={EOA:'0',D6:'109160000'}
    assert r['name']=='Polymarket USD' and r['block_hash_rechecked'] and len(p.calls)==8
    assert {x['params'][1] for x in p.calls if x['method']=='eth_call'}=={'0x123'}
    assert p.calls[-1]['params']==['0x123',False]

@pytest.mark.parametrize('change',['chain','stale','reorg','symbol','decimals'])
def test_chain_metadata_freshness_and_reorg_fail_closed(monkeypatch,change):
    r,p=run(monkeypatch,change)
    assert r['status']=='BLOCKED' and 'balances_raw' not in r

@pytest.mark.parametrize('method,params',[
    ('eth_sendRawTransaction',['0x00']),('personal_sign',[]),('eth_sign',[]),('eth_getLogs',[]),('eth_getCode',[CONTRACT,'0x123']),('eth_getTransactionReceipt',['0x'+'a'*64]),
    ('eth_call',[{'to':CONTRACT,'data':'0x095ea7b3'},'0x123']),
    ('eth_call',[{'to':CONTRACT,'data':'0x70a08231'+'3'*64},'0x123']),
    ('eth_call',[{'to':CONTRACT,'data':'0x313ce567','value':'0x0'},'0x123']),
    ('eth_call',[{'to':CONTRACT,'data':'0x313ce567'},'latest']),
    ('eth_call',[{'to':CONTRACT,'data':'0x313ce567'},'0x124']),
    ('eth_call',[{'to':CONTRACT,'data':[]},'0x123']),
    ('eth_getBlockByNumber',['latest',False]),('eth_getBlockByNumber',['0x123',True])])
def test_forbidden_rpc_never_constructs_request(monkeypatch,method,params):
    def forbidden(*a,**kw):raise AssertionError('REQUEST_CONSTRUCTION_FORBIDDEN')
    monkeypatch.setattr('urllib.request.Request',forbidden)
    r=PinnedCashRPC();r.pin={'number_hex':'0x123'}
    with pytest.raises(ValueError):r.call(method,params)
    assert not r.calls

def test_call_before_pin_is_forbidden():
    with pytest.raises(ValueError):PinnedCashRPC().call('eth_call',[{'to':CONTRACT,'data':'0x313ce567'},'0x123'])

def test_network_failure_halts_no_retry(monkeypatch):
    class Fail:
        def open(self,*a,**kw):raise TimeoutError('private-endpoint-CANARY')
    monkeypatch.setattr('urllib.request.build_opener',lambda *a:Fail())
    r=PinnedCashRPC()
    with pytest.raises(RuntimeError):r.call('eth_chainId',[])
    with pytest.raises(ValueError):r.call('eth_chainId',[])
    assert len(r.calls)==1 and 'CANARY' not in str(r.calls)

def test_economic_account_identity_is_not_overall_readiness(monkeypatch):
    c,_=run(monkeypatch)
    r={'chain':c,'before':{EOA:'0',D6:'109160000'},'after':{EOA:'0',D6:'109160000'},'identity':{'artifact_identity_confirmed':True,'genesis_identity_confirmed':True},'finished_ms':int(time.time()*1000)}
    decision=assess(r)
    assert decision['status']=='ACCOUNT_IDENTIFIED' and decision['reconciliation_account']==D6 and decision['signer']==EOA
    assert not decision['calibration_ready'] and not decision['submit_allowed']
    for key in ('before','after'):
        bad=copy.deepcopy(r);bad[key][D6]='1'
        assert assess(bad)['status']=='CALIBRATION_BLOCKED'
    both=copy.deepcopy(r)
    for rows in (both['before'],both['after'],both['chain']['balances_raw']):rows[EOA]='1'
    assert assess(both)['status']=='CALIBRATION_BLOCKED'
    inverse=copy.deepcopy(r)
    for rows in (inverse['before'],inverse['after'],inverse['chain']['balances_raw']):rows[EOA]='5';rows[D6]='0'
    assert assess(inverse)['reconciliation_account']==EOA

@pytest.mark.parametrize('raw',['0x00',word(32),text_abi('pUSD')+'00'])
def test_malformed_metadata_is_not_accepted(raw):
    with pytest.raises(ValueError):abi_text(raw)
