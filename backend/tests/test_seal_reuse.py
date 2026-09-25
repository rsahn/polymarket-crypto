import pytest
from app.live.ctf_inventory_probe import scan_ctf

def test_scan_exposes_actual_final_numeric_witness(monkeypatch):
    import app.live.ctf_inventory_probe as c
    clock=[1000];calls=[]
    monkeypatch.setattr('time.time_ns',lambda:clock[0]*1000000)
    class RPC:
        wallet='0x'+'1'*40
        def call(self,m,p):
            calls.append(m);clock[0]+=10
            if m=='eth_chainId':return '0x89'
            if m=='eth_getCode':return '0x12'
            if m=='eth_getLogs':return []
            return {'number':'0xc','hash':'0x'+'a'*64,'timestamp':'0x1'}
    captured={};r=scan_ctf(RPC(),11,12,set(),capture=captured)
    assert r['status']=='PASS_SCOPED_READS'
    assert captured['final_numeric_witness']=={'header':{'number':'0xc','hash':'0x'+'a'*64,'timestamp':'0x1'},'started_ms':1040,'received_ms':1050}
    assert calls[-1]=='eth_getBlockByNumber'

@pytest.mark.parametrize('bad',[False,True])
def test_reuse_witness_does_not_reread_or_retime(bad):
    import asyncio
    from analysis.qualify_post_b_proofs import seal_tail
    target={'number':12,'hash':'0x'+'a'*64,'timestamp':1}
    tail={'observed_ms':1000,'final_numeric_witness':{'header':{'number':'0xc','hash':'0x'+('b' if bad else 'a')*64,'timestamp':'0x1'},'started_ms':1100,'received_ms':1170}}
    class RPC:
        def call(self,*a):raise AssertionError('UNNECESSARY_RPC')
    if bad:
        with pytest.raises(ValueError,match='BOUNDARY_REORG'):asyncio.run(seal_tail(RPC(),tail,target))
    else:
        assert asyncio.run(seal_tail(RPC(),tail,target))==(1100,1170,'SCAN_FINAL_NUMERIC_WITNESS')
        assert tail['observed_ms']==1000

def test_empty_tail_discards_old_witness():
    from analysis.qualify_post_b_proofs import fixed_scan
    target={'number':12,'hash':'0x'+'a'*64,'timestamp':1}
    previous={'to_block':12,'block_hash':target['hash'],'observed_ms':1,'final_numeric_witness':{'old':True}}
    class RPC:
        def call(self,*a):return {'number':'0xc','hash':target['hash'],'timestamp':'0x1'}
    result,ranges=fixed_scan(RPC(),previous,target)
    assert ranges==[] and 'final_numeric_witness' not in result and result['observed_ms']==1


def test_witness_cannot_predate_actual_scan():
    import asyncio
    from analysis.qualify_post_b_proofs import seal_tail
    tail={'observed_ms':1200,'final_numeric_witness':{'started_ms':1100,'received_ms':1170}}
    with pytest.raises(ValueError,match='BOUNDARY_SCHEMA_INVALID'):asyncio.run(seal_tail(None,tail,{}))
