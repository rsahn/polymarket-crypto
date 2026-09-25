import pytest
from app.live.fixed_boundary import evaluate_boundary


def evidence():
    return dict(generation=1, finalized_qualified=True, cursor_previous=8,
        anchor_number=10, boundary_number=12, anchor_hash='0x'+'a'*64,
        anchor_rechecked_hash='0x'+'a'*64, boundary_hash='0x'+'b'*64,
        boundary_rechecked_hash='0x'+'b'*64, anchor_ranges=[[9,10]],
        tail_ranges=[[11,12]], rpc_complete=True, events_count=0,
        balances={}, scan_observed_ms=1000, sealed_ms=1100, rechecked_ms=1200,
        account={k:dict(generation=1, complete=True, observed_ms=1150)
                 for k in ('balance','orders','trades','positions')})


@pytest.mark.parametrize('advance',[1,10])
def test_later_head_does_not_invalidate_fixed_coverage(advance):
    e=evidence();e['latest_after']=12+advance
    r=evaluate_boundary(e,now=1300)
    assert r['inventory_through_C_proven'] and r['boundary_generation_complete']
    assert not r['current_inventory_proven'] and not r['submit_allowed']
    assert r['reason']=='POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN'


@pytest.mark.parametrize('change,reason',[
    ({'boundary_rechecked_hash':'0x'+'c'*64},'BOUNDARY_REORG'),
    ({'anchor_rechecked_hash':'0x'+'c'*64},'ANCHOR_REORG'),
    ({'tail_ranges':[[12,12]]},'COVERAGE_GAP_OR_OVERLAP'),
    ({'tail_ranges':[[11,11],[11,12]]},'COVERAGE_GAP_OR_OVERLAP'),
    ({'anchor_ranges':[]},'COVERAGE_GAP_OR_OVERLAP'),
    ({'rpc_complete':False},'RPC_PARTIAL'),
    ({'scan_observed_ms':799},'GENERATION_STALE_500MS'),
    ({'events_count':1},'RECOVERY_REQUIRED'),
    ({'balances':{'123':'1'}},'RECOVERY_REQUIRED'),
    ({'cursor_previous':11},'CURSOR_BOUNDARY_INCOHERENT'),
    ({'boundary_number':9},'CURSOR_BOUNDARY_INCOHERENT'),
    ({'sealed_ms':1190},'ACQUISITION_ORDER_INVALID'),
])
def test_boundary_fail_closed(change,reason):
    e=evidence();e.update(change);r=evaluate_boundary(e,now=1300)
    assert r['reason']==reason
    assert not r['boundary_generation_complete'] and not r['current_inventory_proven']


@pytest.mark.parametrize('field,value',[('complete',False),('generation',2),('observed_ms',1000)])
def test_partial_mixed_or_preseal_account(field,value):
    e=evidence();e['account']['positions'][field]=value
    assert not evaluate_boundary(e,now=1300)['boundary_generation_complete']


def test_no_claim_of_current_even_if_canonical_empty_and_all_sources_complete():
    r=evaluate_boundary(evidence(),now=1500)
    assert r['boundary_generation_complete']
    assert not r['current_inventory_proven'] and not r['ready_for_arm']
    assert not evaluate_boundary(evidence(),now=1501)['boundary_generation_complete']


def test_missing_account_component():
    e=evidence();del e['account']['trades']
    assert evaluate_boundary(e,now=1300)['reason']=='ACCOUNT_GENERATION_PARTIAL'


@pytest.mark.parametrize('reorg',[False,True])
def test_acquisition_selects_c_once_and_never_refreshes_scan_time(monkeypatch,reorg):
    import asyncio
    import analysis.qualify_post_b_proofs as p
    import analysis.qualify_post_genesis as q
    calls=[]
    def h(n):return {'number':hex(n),'hash':'0x'+('a' if n==10 else 'b')*64,'timestamp':'0x1'}
    class RPC:
        def call(self,method,args):
            calls.append(args[0])
            value=h(12 if args[0]=='latest' else int(args[0],16))
            if reorg and args[0]=='0xa':value['hash']='0x'+'c'*64
            return value
    class Geo:
        async def read(self):return {}
    async def views(client):
        assert '0xc' in calls  # numeric seal must precede every account request
        return {k:([],1150) for k in ('balance','orders','trades','positions')}
    anchored=dict(from_block=9,to_block=10,block_hash='0x'+'a'*64,balances={},
                  cursor_previous=8,anchor_catchup_ranges=[[9,10]],observed_ms=1000)
    monkeypatch.setattr(q,'fresh_views',views)
    monkeypatch.setattr(p,'now_ms',lambda:1100)
    monkeypatch.setattr(p,'fixed_scan',lambda *a:({**anchored,'to_block':12,'block_hash':'0x'+'b'*64,
                                                'events_count':0,'observed_ms':1000},[[11,12]]))
    def acquire():return asyncio.run(p.acquire_post_b(None,Geo(),RPC(),anchored,
        {'status':'PASS_PROVIDER_FINALIZED_READ','anchor':{'number':10,'hash':'0x'+'a'*64}}))
    if reorg:
        with pytest.raises(ValueError,match='ANCHOR_REORG'):acquire()
        return
    obs,geo,inv=acquire()
    assert calls.count('latest')==1
    assert inv['observed_ms']==1000
    assert not inv['post_b_proof']['current_inventory_proven']

@pytest.mark.parametrize('scan_status,event_count', [('BLOCKED',0),('PASS_SCOPED_READS',1)])
def test_actual_scanner_partial_or_event_cannot_be_accepted(monkeypatch,scan_status,event_count):
    import analysis.qualify_post_b_proofs as p
    class RPC:
        log_window=10
        def call(self,*a):return {'number':'0xa','hash':'0x'+'a'*64,'timestamp':'0x1'}
    def scan(*a,capture):
        capture['balances']={}
        return {'status':scan_status,'block_hash':'0x'+'b'*64,'events_count':event_count}
    monkeypatch.setattr(p,'scan_ctf',scan)
    with pytest.raises(ValueError,match='TAIL_SCAN_FAILED' if scan_status=='BLOCKED' else 'RECOVERY_REQUIRED'):
        p.fixed_scan(RPC(),{'to_block':10,'block_hash':'0x'+'a'*64,'balances':{}},
                     {'number':12,'hash':'0x'+'b'*64})


@pytest.mark.parametrize('bad_number',[9,13])
def test_actual_scanner_never_rewinds_or_accepts_wrong_cursor_header(monkeypatch,bad_number):
    import analysis.qualify_post_b_proofs as p
    class RPC:
        def call(self,*a):return {'number':hex(bad_number),'hash':'0x'+'a'*64,'timestamp':'0x1'}
    with pytest.raises(ValueError,match='CURSOR_REORG'):
        p.fixed_scan(RPC(),{'to_block':10,'block_hash':'0x'+'a'*64,'balances':{}},
                     {'number':12,'hash':'0x'+'b'*64})

@pytest.mark.parametrize('key', ['scan_observed_ms','sealed_ms','rechecked_ms'])
def test_future_boundary_timestamp_never_admissible(key):
    e=evidence();e[key]=1301
    r=evaluate_boundary(e,now=1300)
    assert not r['boundary_generation_complete'] and not r['current_inventory_proven']
