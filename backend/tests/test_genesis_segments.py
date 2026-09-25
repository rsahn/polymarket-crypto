import pytest
from app.live import genesis_discovery as d

class RPC:
    wallet='fixture'
    def __init__(self,reorg=False):self.latest=0;self.reorg=reorg
    def call(self,m,p):
        if m=='eth_chainId':return '0x89'
        if m=='eth_getBlockByNumber':
            if p[0]=='latest':
                self.latest+=1;n=90573 if self.latest==1 else 90580
            else:n=int(p[0],16)
            h=('b' if self.reorg and self.latest>1 and n==90573 else 'a')*64
            return {'number':hex(n),'hash':'0x'+h,'timestamp':'0x1'}
        raise AssertionError(m)

def setup(monkeypatch,fail=False):
    calls=[]
    monkeypatch.setattr(d,'code_onset',lambda *a:10)
    def scan(rpc,start,end,known,*,capture):
        calls.append((start,end,set(known)))
        assert end-start<50000
        if fail and len(calls)==2:return {'status':'BLOCKED'}
        capture['balances']={**{k:'0' for k in known},'123':'0'}
        return {'status':'PASS_SCOPED_READS','to_block':end,'block_hash':'0x'+'a'*64,'events_count':1,'assets_checked':len(capture['balances'])}
    monkeypatch.setattr(d,'scan_ctf',scan)
    return calls

def test_segmented_discovery_contiguous_and_final_balance_union(monkeypatch):
    calls=setup(monkeypatch)
    r=d.segmented_snapshot(RPC(),set())
    assert [(a,b) for a,b,_ in calls]==[(10,50009),(50010,90573),(90574,90580)]
    assert calls[-1][2]=={'123'}
    assert r['to_block']==90580 and r['balances']=={'123':'0'}
    assert r['complete'] is False and len(r['chunk_manifest'])==3

@pytest.mark.parametrize('failure',['scan','reorg'])
def test_segment_failure_never_returns_genesis_evidence(monkeypatch,failure):
    setup(monkeypatch,fail=failure=='scan')
    with pytest.raises(d.DiscoveryBlocked):d.segmented_snapshot(RPC(reorg=failure=='reorg'),set())

def test_total_budget_refused_before_scan(monkeypatch):
    calls=setup(monkeypatch)
    monkeypatch.setattr(d,'code_onset',lambda *a:0)
    class TooWide(RPC):
        def call(self,m,p):
            result=super().call(m,p)
            if m=='eth_getBlockByNumber':result['number']=hex(200000)
            return result
    with pytest.raises(d.DiscoveryBlocked):d.segmented_snapshot(TooWide(),set())
    assert not calls

@pytest.mark.parametrize('head',[90573,95574,90572])
def test_single_catchup_is_bounded(monkeypatch,head):
    calls=setup(monkeypatch)
    class R(RPC):
        def call(self,m,p):
            r=super().call(m,p)
            if m=='eth_getBlockByNumber' and p[0]=='latest' and self.latest>1:r['number']=hex(head)
            return r
    if head==90573:
        result=d.segmented_snapshot(R(),set())
        assert calls[-1][:2]==(90573,90573)
        assert result['to_block']==head
    else:
        with pytest.raises(d.DiscoveryBlocked):d.segmented_snapshot(R(),set())
        assert len(calls)==2

def test_final_nonzero_balance_preserved_for_recovery(monkeypatch):
    setup(monkeypatch)
    original=d.scan_ctf
    def scan(rpc,start,end,known,*,capture):
        r=original(rpc,start,end,known,capture=capture)
        if end==90580:capture['balances']['123']='7'
        return r
    monkeypatch.setattr(d,'scan_ctf',scan)
    assert d.segmented_snapshot(RPC(),set())['balances']['123']=='7'
