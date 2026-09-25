import asyncio
import json
import pytest
from app.live import forward_readiness as f
from app.live.readonly_book_stream import StreamBook


def generation():
    return {'id':1,'ledger_hash':'a'*64,'watermark':{'block_number':12,'block_hash':'b'*64},
        'components':{n:{'generation':1,'observed_ms':1000,'complete':True} for n in
                      ('balance','orders','trades','positions','inventory')}}

@pytest.mark.parametrize('age,ok',[(499,True),(501,False),(2759,False)])
def test_generation_age(age,ok):
    assert f.validate_generation(generation(),1000+age)['complete'] is ok

@pytest.mark.parametrize('mutation',['missing','partial','mixed','future','watermark'])
def test_generation_incomplete(mutation):
    g=generation()
    if mutation=='missing':del g['components']['trades']
    if mutation=='partial':g['components']['orders']['complete']=False
    if mutation=='mixed':g['components']['balance']['generation']=2
    if mutation=='future':g['components']['balance']['observed_ms']=1200
    if mutation=='watermark':g['watermark']={}
    assert not f.validate_generation(g,1100)['complete']


def event(token='1',stamp=1000):
    return {'event_type':'book','market':'condition','asset_id':token,'timestamp':str(stamp),
            'bids':[{'price':'.4','size':'2'}],'asks':[{'price':'.6','size':'2'}]}


def stream():return StreamBook('slug','condition',('1','2'),5000,clock=lambda:1000)


def test_ws_states_and_resync():
    s=stream();assert not s.read()['available']
    s.connected_generation();assert not s.read()['available']
    s.ingest(event());assert not s.read()['available']
    s.ingest(event('2'));assert s.read()['available']
    first=s.generation;s.disconnect();assert not s.read()['available']
    s.connected_generation();assert not s.read()['available']
    s.ingest(event());assert not s.read()['available']
    s.ingest(event('2'));assert s.read()['available'] and s.generation>first
    assert s.read()['diagnostics']['resync_complete_generation']==s.generation


class Socket:
    calls=0
    async def send(self,value):pass
    async def recv(self):
        self.calls+=1
        if self.calls>1:raise OSError('fixture disconnect')
        return json.dumps(event(stamp=499))
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass


def test_parser_cause_survives_run_cleanup():
    s=stream()
    asyncio.run(s.run(connect_factory=lambda *a,**k:Socket()))
    r=s.read()
    assert r['reason']=='STALE_WIRE_EVENT'
    assert not r['connected']
    assert r['diagnostics']['parser_reason']=='STALE_WIRE_EVENT'


def test_valid_depth_diagnostics_survive_disconnect():
    s=stream();s.connected_generation();s.ingest(event());s.ingest(event('2'));s.disconnect()
    d=s.read()['diagnostics']
    assert d['last_valid_message']['kind']=='book'
    assert len(d['tokens'])==2 and all(t['last_valid_book_ms']==1000 for t in d['tokens'])
    assert all(t['last_valid_book_age_ms']==0 for t in d['tokens'])
    assert 'asset_id' not in json.dumps(d)


def test_slow_inventory_is_prepared_before_account(monkeypatch):
    import analysis.qualify_post_genesis as q
    calls=[]
    def advance(*a):calls.append('inventory');return {'observed_ms':1}
    async def views(*a):calls.append('account');return {}
    class Geo:
        async def read(self):calls.append('geo');return {}
    monkeypatch.setattr(q,'advance_inventory',advance);monkeypatch.setattr(q,'fresh_views',views)
    monkeypatch.setattr(q,'witness_inventory',lambda *a:{'observed_ms':1})
    _,_,inv=asyncio.run(q.acquire_final_views(None,Geo(),None,None,None))
    assert calls.index('inventory')<calls.index('account') and calls.index('geo')<calls.index('account')
    assert inv['observed_ms']==1


@pytest.mark.parametrize('age,partial,expected',[(499,False,True),(501,False,False),(100,True,False)])
def test_full_readiness_generation_gate(age,partial,expected,monkeypatch):
    from app.live.readiness import ProductionReadinessCheck
    from app.live.forward_readiness import ObservationSource
    for key in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED'):monkeypatch.setenv(key,'false')
    g=generation()
    if partial:del g['components']['trades']
    source=lambda **kw:ObservationSource({'available':True,'observed_ms':1000,**kw})
    s=stream();s.connected_generation();s.ingest(event());s.ingest(event('2'))
    r=asyncio.run(ProductionReadinessCheck(account=source(authenticated=True,balance_usdc='100',allowance_usdc='100',complete=True,open_order_ids=[]),
        positions=source(complete=True,balances={}),book=s,geo=source(blocked=False),risk=source(allow=True),
        local_reader=lambda:{'phase':'GENESIS_RECONCILED','integrity_verified':True,'reconciled_now':True},
        clock=lambda:1000+age,generation=g).run())
    assert len(r['checks'])==12 and r['ready_for_arm'] is expected and not r['submit_allowed']


def test_remote_close_code_and_reason_redacted():
    from websockets.exceptions import ConnectionClosedError
    from websockets.frames import Close
    class Closed(Socket):
        async def recv(self):raise ConnectionClosedError(Close(1008,'SECRET_SENTINEL'),None)
    s=stream();asyncio.run(s.run(connect_factory=lambda *a,**k:Closed()))
    r=s.read();d=r['diagnostics']
    assert d['close_code']==1008 and d['close_reason_category']=='REMOTE_CLOSE_FRAME'
    assert d['remote_close_reason_present'] and 'SECRET_SENTINEL' not in json.dumps(r)


@pytest.mark.parametrize("health_contract,empty",[(False,False),(True,False),(True,True)])
def test_qualifier_evaluates_before_ws_shutdown(monkeypatch,health_contract,empty):
    import analysis.qualify_post_genesis as q
    from app.live.readiness import ProductionReadinessCheck
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    for key in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED'):monkeypatch.setenv(key,'false')
    monkeypatch.setenv('POLYGON_ARCHIVE_RPC_URL','https://example.invalid')
    prior={'phase':'GENESIS_RECONCILED','integrity_verified':True,'event_count':0,'last_hash':'a'*64,'snapshot_sha256':'c'*64,
        'snapshot':{'wallet':'wallet','block_number':10,'block_hash':'d'*64,'collateral':{'contract':q.CONTRACT,'balance_raw':'109160000'},'conditional_assets':{'balances':{}}}}
    inv={'from_block':11,'to_block':12,'block_hash':'b'*64,'events_count':0,'assets_checked':0,'observed_ms':1000,'provenance':'FAKE','balances':{}}
    monkeypatch.setattr(q,'read_genesis',lambda *a:prior)
    monkeypatch.setattr(q,'expected_wallet',lambda:'wallet')
    monkeypatch.setattr(q,'now_ms',lambda:1000)
    monkeypatch.setattr(q,'incremental_inventory',lambda *a:inv)
    monkeypatch.setattr(q,'load_inventory_cursor',lambda *a:inv)
    monkeypatch.setattr(q,'save_inventory_cursor',lambda *a:None)
    monkeypatch.setattr(q,'advance_inventory',lambda *a:inv)
    monkeypatch.setattr(q,'witness_inventory',lambda *a:inv)
    class RPC:
        def __init__(self,*a,**k):self.calls=[]
        def call(self,*a):return {"hash":"d"*64}
    monkeypatch.setattr(q,'PublicRPC',RPC)
    monkeypatch.setattr(q,'load_existing',lambda *a:({'apiKey':'FAKE_SENTINEL_KEY','secret':'FAKE_SENTINEL_SECRET','passphrase':'FAKE_SENTINEL_PASS'},{'storage_validated':True}))
    class Get:
        def __init__(self,*a,**k):pass
        async def get_json(self,path):return int(q.time.time())
    monkeypatch.setattr(q,'GetOnlyTransport',Get)
    monkeypatch.setattr(q,'ReadOnlyClient',lambda **kw:None)
    class Geo:
        def __init__(self,*a,**k):pass
        async def read(self):return {'available':True,'observed_ms':1000,'blocked':False}
    monkeypatch.setattr(q,'GeoBlockSource',Geo)
    async def views(*a):return {'balance':({'balance':'109160000','allowances':{env.standard_exchange:'109160000'}},1000),
                               'orders':([],1000),'trades':([],1000),'positions':([],1000)}
    monkeypatch.setattr(q,'fresh_views',views)
    import analysis.qualify_post_b_proofs as proof
    monkeypatch.setattr(proof,'prepare_finalized_inventory',lambda *a:(inv,{'status':'PASS_PROVIDER_FINALIZED_READ'}))
    async def acquired(client,geo,*a,**kw):return await views(),await geo.read(),inv
    monkeypatch.setattr(proof,'acquire_post_b',acquired)
    stopped=[]
    class Active(StreamBook):
        async def run(self):
            self.connected_generation()
            for token in ('1','2'):
                e=event(token)
                if empty:e['asks']=[]
                self.ingest(e)
            try:await asyncio.Future()
            finally:stopped.append(True);self.disconnect()
    s=Active('slug','condition',('1','2'),5000,clock=lambda:1000)
    async def discover(*a):return s
    monkeypatch.setattr(q,'discover_book',discover)
    monkeypatch.setattr(q,'ProductionReadinessCheck',lambda **kw:ProductionReadinessCheck(**kw,clock=lambda:1000))
    r=asyncio.run(q.run(True,health_contract=health_contract))
    assert r['readiness']['ready_for_arm'] is (not empty),r['reconciliation']
    assert r['readiness']['SYSTEM_READY']
    assert r['readiness']['MARKET_ELIGIBLE_NOW'] is (not empty)
    assert r['readiness']['observations']['book']['connected']
    assert stopped and not s.connected and not r['readiness']['submit_allowed']
    assert 'FAKE_SENTINEL' not in json.dumps(r)


def test_local_validation_time_counts_towards_freshness(monkeypatch):
    from app.live.readiness import ProductionReadinessCheck
    from app.live.forward_readiness import ObservationSource
    now=[1000]
    def local():now[0]=1600;return {'phase':'CLOSED'}
    def source(**kw):return ObservationSource({'available':True,'observed_ms':1000,**kw})
    r=asyncio.run(ProductionReadinessCheck(account=source(authenticated=True,balance_usdc='100',allowance_usdc='100',complete=True,open_order_ids=[]),
        positions=source(complete=True,balances={}),book=source(connected=True,book_synced=True),geo=source(blocked=False),risk=source(allow=True),
        local_reader=local,clock=lambda:now[0],generation=generation()).run())
    assert not r['ready_for_arm'] and r['evaluated_ms']==1600
