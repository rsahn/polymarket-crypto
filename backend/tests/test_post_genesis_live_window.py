import asyncio
import pytest
from app.live.readonly_book_stream import StreamBook
from app.live.production_readonly import BookStateSource


def test_book_connection_sync_freshness_separate():
    now=[1000];b=BookStateSource(clock=lambda:now[0]);b.connect('m',('1','2'),1)
    for t in ('1','2'):b.update(t,[('.4','1')],[('.6','1')],1000,1)
    now[0]=1501;r=b.read()
    assert r['connected'] and r['synchronized'] and not r['fresh'] and not r['available']

@pytest.mark.parametrize('bid,ask,reason', [([],[], 'EMPTY_BOOK'),([('.7','1')],[('.6','1')],'CROSSED_BOOK')])
def test_exact_book_reason(bid,ask,reason):
    b=BookStateSource(clock=lambda:1000);b.connect('m',('1','2'),1)
    if reason=='EMPTY_BOOK':
        b.update('1',bid,ask,1000,1);b.update('2',bid,ask,1000,1)
        assert b.read()['reason']=='EMPTY_BOOK' and b.read()['synchronized']
    else:
        with pytest.raises(ValueError,match='^'+reason+'$'):b.update('1',bid,ask,1000,1)
    assert b.connected and not b.read()['available']


def test_stale_wire_invalidates_without_claiming_socket_closed():
    s=StreamBook('m','c',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    with pytest.raises(ValueError):s.ingest({'event_type':'book','market':'c','asset_id':'1','timestamp':'499','bids':[],'asks':[]})
    assert s.connected and not s.read()['available']
    assert s.read()['last_wire_event_ms']==499


def test_fresh_witness_is_real_rpc_not_cached_retiming(monkeypatch):
    import analysis.qualify_post_genesis as q
    prior={'to_block':12,'block_hash':'h','observed_ms':1,'balances':{},'events_count':0}
    class R:
        def call(self,m,p):
            assert (m,p)==('eth_getBlockByNumber',['latest',False])
            return {'number':'0xc','hash':'h','timestamp':'0x1'}
    monkeypatch.setattr(q,'now_ms',lambda:1200)
    r=q.witness_inventory(R(),prior)
    assert r['observed_ms']==1200 and r['scan_observed_ms']==1
    assert prior['observed_ms']==1 and r['head_block_timestamp_ms']==1000


def test_new_head_requires_delta_not_new_timestamp():
    import analysis.qualify_post_genesis as q
    class R:
        def call(self,*a):return {'number':'0xd','hash':'next','timestamp':'0x1'}
    with pytest.raises(ValueError,match='HEAD_ADVANCED'):
        q.witness_inventory(R(),{'to_block':12,'block_hash':'h','observed_ms':1})


def test_same_height_reorg_blocks():
    import analysis.qualify_post_genesis as q
    class R:
        def call(self,*a):return {'number':'0xc','hash':'different','timestamp':'0x1'}
    with pytest.raises(ValueError,match='CURSOR_REORG'):
        q.witness_inventory(R(),{'to_block':12,'block_hash':'h','observed_ms':1})


def test_inventory_witness_timeout_does_not_retime(monkeypatch):
    import analysis.qualify_post_genesis as q
    prior={'to_block':12,'block_hash':'h','observed_ms':1}
    class R:
        def call(self,*a):raise TimeoutError()
    with pytest.raises(TimeoutError):q.witness_inventory(R(),prior)
    assert prior['observed_ms']==1


def test_head_advance_retries_whole_generation_only(monkeypatch):
    import analysis.qualify_post_genesis as q
    seen=[]
    def advance(rpc,prior,old):seen.append('delta');return old
    def witness(*a):
        if seen.count('account')==1:raise ValueError('HEAD_ADVANCED')
        return {'observed_ms':1000}
    async def views(*a):seen.append('account');return {'attempt':seen.count('account')}
    class Geo:
        async def read(self):return {}
    monkeypatch.setattr(q,'advance_inventory',advance);monkeypatch.setattr(q,'witness_inventory',witness);monkeypatch.setattr(q,'fresh_views',views)
    obs,_,inv=asyncio.run(q.acquire_final_views(None,Geo(),None,None,{}))
    assert obs=={'attempt':2} and inv['generation_attempt']==2 and seen==['delta','account','delta','account']


def test_empty_cause_depth_diagnostics_and_resync():
    s=StreamBook('m','c',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    def event(t,bids,asks):return {'event_type':'book','market':'c','asset_id':t,'timestamp':'1000','bids':bids,'asks':asks}
    s.ingest(event('1',[],[]))
    assert not s.read()['available']
    d=s.read()['diagnostics']['tokens'][0]
    assert d['bids_count']==0 and d['asks_count']==0 and d['best_bid'] is None
    for t in ('1','2'):
        s.ingest(event(t,[{'price':'.4','size':'1'}],[{'price':'.6','size':'1'}]))
        if t=='1':assert not s.read()['available']
    assert s.read()['available'] and s.read()['synchronized'] and s.read()['last_valid_book_ms']==1000
