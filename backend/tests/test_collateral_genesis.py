import json
import sqlite3
import pytest
from app.live.collateral_onchain import PublicRPC,qualify_collateral,bind_collateral,CONTRACT,symbol_string
from app.live.genesis_readonly import read_local_ledger,initial_inventory
from app.live.readiness import ProductionReadinessCheck

WALLET='0x'+'1'*40

def word(n):return '0x'+hex(n)[2:].rjust(64,'0')

def symbol():return '0x'+(32).to_bytes(32,'big').hex()+(4).to_bytes(32,'big').hex()+b'pUSD'.ljust(32,b'\0').hex()

class FakeRPC:
    wallet=WALLET
    def __init__(self,chain='0x89',decimals=6,code='0x6000',reorg=False):self.chain=chain;self.decimals=decimals;self.code=code;self.reorg=reorg
    def call(self,m,p):
        if m=='eth_chainId':return self.chain
        if m=='eth_getBlockByNumber':return {'number':'0x10','timestamp':'0x3e8','hash':'0x'+('b' if self.reorg and p[0]!='latest' else 'a')*64}
        if m=='eth_getCode':return self.code
        if m=='eth_call':
            data=p[0]['data']
            return word(self.decimals) if data=='0x313ce567' else symbol() if data=='0x95d89b41' else word(109160000)
        raise AssertionError(m)


def test_metadata_and_nonfloat_conversion_only_after_binding():
    r=qualify_collateral(FakeRPC(),clock=lambda:1001)
    assert r['status']=='PASS_ONCHAIN_IDENTITY' and not r['conversion_allowed']
    r=bind_collateral(r,'109160000','109160000')
    assert r['balance_human']=='109.160000' and r['balance_unit']=='pUSD'
    assert r['account_binding_verified']

@pytest.mark.parametrize('kw',[{'chain':'0x1'},{'decimals':18},{'code':'0x'},{'reorg':True}])
def test_chain_code_decimals_reorg_fail_closed(kw):
    r=qualify_collateral(FakeRPC(**kw),clock=lambda:1001)
    assert r['status']=='BLOCKED' and not bind_collateral(r,'109160000','109160000')['conversion_allowed']


def test_different_balances_do_not_bind():
    r=qualify_collateral(FakeRPC(),clock=lambda:1001)
    assert not bind_collateral(r,'0','109160000')['conversion_allowed']
    assert not bind_collateral(r,'0','0')['conversion_allowed']

@pytest.mark.parametrize('method,params',[('eth_sendRawTransaction',['0xdead']),('eth_sign',[]),('eth_call',[{'to':CONTRACT,'data':'0x095ea7b3'},'0x10']),('eth_call',[{'to':CONTRACT,'data':'0x313ce567','from':WALLET},'0x10'])])
def test_rpc_disallows_transactions_signing_arbitrary_calls(method,params):
    with pytest.raises(ValueError):PublicRPC(WALLET).call(method,params)


def test_malformed_symbol_never_printed():
    with pytest.raises(ValueError):symbol_string('0x'+b'secret'.hex())


def test_missing_ledger_not_flat_and_readiness_has_only_phase_blockers():
    local,assets=read_local_ledger(None)
    i=initial_inventory({'positions':{'count':0}},local)
    assert i['phase']=='GENESIS_RECONCILIATION_PENDING' and not i['complete'] and not assets
    r=ProductionReadinessCheck.qualification_snapshot({'conversion_allowed':False},i,provenance={})
    assert set(r['blockers'])=={'collateral_identity_and_binding','inventory_reconciliation'}
    assert not r['ready_for_arm']


def test_known_assets_from_real_journal_readonly(tmp_path):
    p=tmp_path/'ledger.db'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE execution_state(id INTEGER,value TEXT)')
        db.execute('CREATE TABLE execution_events(id INTEGER,event TEXT,value TEXT)')
        db.execute('INSERT INTO execution_events VALUES(1,?,?)',('entry',json.dumps({'order':{'token_id':'123'}})))
    before=p.read_bytes();local,assets=read_local_ledger(p)
    assert assets=={'123'} and local['known_assets_count']==1 and p.read_bytes()==before
    assert not local['session_history_proven']


def test_ctf_discovers_orphan_and_stays_incomplete():
    from app.live.ctf_inventory_probe import scan_ctf
    from app.live.collateral_onchain import CTF
    from eth_utils import keccak
    from eth_abi import encode
    class CTFake:
        wallet=WALLET
        def call(self,m,p):
            if m=='eth_chainId':return '0x89'
            if m=='eth_getBlockByNumber':return {'number':'0x10','hash':'0x'+'a'*64}
            if m=='eth_getCode':return '0x6000'
            if m=='eth_getLogs':return [{'removed':False,'address':CTF,'topics':['0x'+keccak(text='TransferSingle(address,address,address,uint256,uint256)').hex(),'0x'+'0'*64,'0x'+'0'*64,'0x'+WALLET[2:].rjust(64,'0')],'blockNumber':'0x10','transactionHash':'0x'+'b'*64,'logIndex':'0x0','data':'0x'+encode(['uint256','uint256'],[123,7]).hex()}]
            if m=='eth_call':return word(7)
            raise AssertionError()
    r=scan_ctf(CTFake(),16,16,set())
    assert r['status']=='PASS_SCOPED_READS' and r['nonzero_assets']==1
    assert r['discovered_outside_local_journal']==1 and r['complete'] is False


def test_ctf_range_limit_prevents_network():
    from app.live.ctf_inventory_probe import scan_ctf
    class Never:
        def call(self,*a):raise AssertionError()
    assert scan_ctf(Never(),0,50000,set())['status']=='BLOCKED'


def test_rpc_never_posts_to_clob_and_rejects_wrong_response_id(monkeypatch):
    import urllib.request
    from app.live.collateral_onchain import RPC
    calls=[]
    class R:
        status=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return b'{"jsonrpc":"2.0","id":999,"result":"0x89"}'
    class O:
        def open(self,request,timeout):calls.append(request);return R()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:O())
    with pytest.raises(RuntimeError):PublicRPC(WALLET).call('eth_chainId',[])
    assert calls[0].full_url==RPC and calls[0].method=='POST'
    assert json.loads(calls[0].data)['method']=='eth_chainId'
