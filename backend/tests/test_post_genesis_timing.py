import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest


def test_parallel_rpc_response_ids_are_request_local(monkeypatch):
    import app.live.collateral_onchain as c
    barrier=threading.Barrier(2)
    class Response:
        status=200
        def __init__(self,request):self.payload=json.loads(request.data)
        def __enter__(self):barrier.wait(timeout=3);return self
        def __exit__(self,*a):pass
        def read(self,*a):return json.dumps({'jsonrpc':'2.0','id':self.payload['id'],'result':'0x89'}).encode()
    class Opener:
        def open(self,request,**kw):return Response(request)
    monkeypatch.setattr(c.urllib.request,'build_opener',lambda *a:Opener())
    rpc=c.PublicRPC('0x'+'1'*40,endpoint='https://example.invalid')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(rpc.call,'eth_chainId',[]) for _ in range(2)]
        assert [f.result() for f in futures]==['0x89','0x89']
    assert {x['id'] for x in rpc.calls}=={1,2}
    assert all(x['finished_ms']>=x['started_ms'] for x in rpc.calls)


def test_final_boundary_rechecks_overlap_and_preserve_clock(monkeypatch):
    import analysis.qualify_post_b_proofs as p
    clock=[1000];started=[]
    async def thread(fn,*args):
        started.append(args[1][0]);await asyncio.sleep(0)
        # Two independent requests in one deterministic 220ms wave.
        clock[0]=1220
        return fn(*args)
    class RPC:
        def call(self,m,args):return {'number':args[0],'hash':'0x'+'a'*64,'timestamp':'0x1'}
    monkeypatch.setattr(p.asyncio,'to_thread',thread)
    monkeypatch.setattr(p,'now_ms',lambda:clock[0])
    check,anchor,timing=asyncio.run(p.recheck_fixed_boundary(RPC(),12,10))
    assert set(started)=={'0xc','0xa'}
    assert timing['started_ms']==1000 and timing['finished_ms']==1220
    assert check['number']==12 and anchor['number']==10

@pytest.mark.parametrize('age,complete',[(500,True),(501,False)])
def test_parallel_recheck_does_not_refresh_inventory(age,complete):
    from app.live.fixed_boundary import evaluate_boundary
    e=dict(generation=1,finalized_qualified=True,cursor_previous=10,anchor_number=10,boundary_number=11,
        anchor_hash='0x'+'a'*64,anchor_rechecked_hash='0x'+'a'*64,
        boundary_hash='0x'+'b'*64,boundary_rechecked_hash='0x'+'b'*64,
        anchor_ranges=[],tail_ranges=[[11,11]],rpc_complete=True,events_count=0,balances={},
        scan_observed_ms=1000,sealed_ms=1100,rechecked_ms=1300,
        account={k:dict(generation=1,complete=True,observed_ms=1200) for k in ('balance','orders','trades','positions')})
    result=evaluate_boundary(e,now=1000+age)
    assert result['boundary_generation_complete'] is complete
    assert not result['current_inventory_proven']
    assert e['scan_observed_ms']==1000


@pytest.mark.parametrize('invalid',[None,'chain','code','logs'])
def test_fixed_range_independent_rpc_reads_overlap(invalid):
    from app.live.ctf_inventory_probe import scan_ctf
    gate=threading.Barrier(4)
    class RPC:
        wallet='0x'+'1'*40
        log_window=10
        parallel_inventory_reads=True
        def __init__(self):self.headers=0
        def call(self,method,params):
            if method=='eth_getBlockByNumber':
                self.headers+=1
                if self.headers>1:return {'number':'0xc','hash':'0x'+'a'*64}
            gate.wait(timeout=1)
            if method=='eth_chainId':return '0x1' if invalid=='chain' else '0x89'
            if method=='eth_getCode':return '0x' if invalid=='code' else '0x1234'
            if method=='eth_getLogs':return {} if invalid=='logs' else []
            return {'number':'0xc','hash':'0x'+'a'*64}
    r=scan_ctf(RPC(),11,12,set(),capture={})
    assert r['status']==('PASS_SCOPED_READS' if invalid is None else 'BLOCKED')
