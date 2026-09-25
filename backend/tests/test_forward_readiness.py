import pytest
from app.live.forward_readiness import evaluate_baseline
from app.live.readonly_book_stream import StreamBook


def baseline():
    return {'phase':'GENESIS_RECONCILED','integrity_verified':True,'event_count':0,'snapshot':{
        'wallet':'wallet','block_number':10,'block_hash':'h','collateral':{'balance_raw':'109160000'},
        'conditional_assets':{'balances':{}}}}

def remote():
    return {'wallet':'wallet','balance_raw':'109160000','orders':[],'trades':[],'positions':[],
            'balances':{},'events_count':0,'complete':True,'observed_ms':1000}

def test_baseline_reconciliation_uses_actual_balance():
    r=evaluate_baseline(baseline(),remote(),now=1100)
    assert r['reconciled'] and r['cash_collateral']=='109.16' and r['net_pnl']=='0'

@pytest.mark.parametrize('field,value',[('balance_raw','109160001'),('orders',[{}]),('trades',[{}]),('positions',[{}]),('balances',{'1':'2'}),('events_count',1)])
def test_unexplained_delta_requires_recovery(field,value):
    r=remote();r[field]=value
    assert evaluate_baseline(baseline(),r,now=1100)['phase']=='RECOVERY_REQUIRED'

def test_stale_evidence_is_not_reconciliation():
    assert not evaluate_baseline(baseline(),remote(),now=1501)['reconciled']

def test_unmodelled_ledger_activity_blocks():
    b=baseline();b['event_count']=1
    assert not evaluate_baseline(b,remote(),now=1100)['reconciled']

def test_two_ws_snapshots_reconnect_and_expiry():
    now=[1000];s=StreamBook('slug','condition',('1','2'),5000,clock=lambda:now[0])
    s.connected_generation()
    def book(t):return {'event_type':'book','market':'condition','asset_id':t,'timestamp':'1000','bids':[{'price':'.4','size':'2'}],'asks':[{'price':'.6','size':'2'}]}
    s.ingest(book('1'));assert not s.read()['book_synced']
    s.ingest(book('2'));assert s.read()['book_synced']
    s.disconnect();assert not s.read()['book_synced']
    s.connected_generation();s.ingest(book('1'));assert not s.read()['book_synced']
    s.ingest(book('2'));now[0]=1501;assert not s.read()['available']


def test_foreign_identity_invalidates_stream():
    s=StreamBook('slug','condition',('1','2'),5000,clock=lambda:1000)
    s.connected_generation()
    with pytest.raises(ValueError):s.ingest({'event_type':'book','market':'other'})
    assert not s.read()['connected']


def test_partial_delta_never_bootstraps_a_book():
    s=StreamBook('slug','condition',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    s.ingest({'event_type':'price_change','market':'condition','timestamp':'1000','price_changes':[{'asset_id':'1','side':'BUY','price':'.4','size':'2'}]})
    assert not s.read()['book_synced']

@pytest.mark.parametrize('stamp',[499,1001])
def test_old_or_future_wire_timestamp_fails_closed(stamp):
    s=StreamBook('slug','condition',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    with pytest.raises(ValueError):s.ingest({'event_type':'book','market':'condition','asset_id':'1','timestamp':str(stamp),'bids':[],'asks':[]})
    assert not s.read()['connected']


def test_forward_risk_requires_reconciled_fresh_ledger():
    from app.live.forward_readiness import ForwardSessionRiskSource
    r=evaluate_baseline(baseline(),remote(),now=1100)
    assert ForwardSessionRiskSource(r,lambda:1100).read()['allow']
    assert not ForwardSessionRiskSource(r,lambda:1600).read()['available']


def test_post_genesis_scan_never_includes_genesis(monkeypatch):
    import analysis.qualify_post_genesis as q
    b=baseline()
    class R:
        def call(self,m,p):
            if m=='eth_chainId':return '0x89'
            if p[0]=='0xa':return {'hash':'h'}
            return {'number':'0xc','hash':'next','timestamp':'0x1'}
    ranges=[]
    def scan(rpc,start,end,known,*,capture):
        ranges.append((start,end));capture['balances']={}
        return {'status':'PASS_SCOPED_READS','block_hash':'next','from_block':start,'to_block':end,'events_count':0,'assets_checked':0}
    monkeypatch.setattr(q,'scan_ctf',scan)
    assert q.incremental_inventory(R(),b)['balances']=={}
    assert ranges==[(11,12)]


def test_offline_full_report_does_not_load_credentials_or_network(monkeypatch):
    import asyncio
    import analysis.qualify_post_genesis as q
    b=baseline();b['snapshot_sha256']='a'*64;b['last_hash']='a'*64
    monkeypatch.setattr(q,'read_genesis',lambda *a:b)
    def forbidden(*a,**kw):raise AssertionError('FORBIDDEN')
    monkeypatch.setattr(q,'load_existing',forbidden);monkeypatch.setattr(q,'PublicRPC',forbidden)
    r=asyncio.run(q.run(False))
    assert r['genesis_unchanged'] and not r['genesis_created']
    assert len(r['readiness']['checks'])==12 and not r['readiness']['ready_for_arm']
    assert not r['readiness']['submit_allowed']

@pytest.mark.parametrize('bad',[{'bids':[{'price':'.7','size':'2'}],'asks':[{'price':'.6','size':'2'}]}, {'bids':[{'price':'.4','size':'2'},{'price':'.4','size':'3'}],'asks':[{'price':'.6','size':'2'}]}])
def test_crossed_or_duplicate_depth_invalidates(bad):
    s=StreamBook('slug','condition',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    with pytest.raises(ValueError):s.ingest({'event_type':'book','market':'condition','asset_id':'1','timestamp':'1000',**bad})
    assert not s.read()['connected']


def test_reconnect_generation_is_monotone():
    s=StreamBook('slug','condition',('1','2'),5000,clock=lambda:1000)
    s.connected_generation();first=s.generation;s.disconnect();s.connected_generation()
    assert s.generation>first


def test_freshness_never_overrides_real_divergence():
    r=remote();r['balance_raw']='0'
    assert evaluate_baseline(baseline(),r,now=5000)['phase']=='RECOVERY_REQUIRED'


def test_incremental_genesis_reorg_stops_before_event_reads():
    import analysis.qualify_post_genesis as q
    class R:
        def call(self,m,p):
            if m=='eth_chainId':return '0x89'
            assert m=='eth_getBlockByNumber' and p[0]=='0xa'
            return {'hash':'reorg'}
    with pytest.raises(ValueError,match='GENESIS_ANCHOR_CHANGED'):q.incremental_inventory(R(),baseline())
