import json
import pytest
from app.live.readonly_book_stream import StreamBook


def event(t='1',asks=None):
    return {'event_type':'book','asset_id':t,'market':'c','timestamp':'1000',
        'bids':[{'price':'.4','size':'2'}],'asks':[{'price':'.6','size':'2'}] if asks is None else asks}


def test_first_wire_book_recorded_with_empty_market_ineligible():
    s=StreamBook('m','c',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    s.ingest(event(asks=[]));assert not s.read()['market_eligible']
    first=s.read()['diagnostics']['first_full_books'][0]
    assert first['bids_count']==1 and first['asks_count']==0 and first['source_timestamp_ms']==1000
    assert first['token_index']==0 and first['identity_matches'] and first['message_kind']=='book'
    s.ingest(event());assert s.read()['diagnostics']['first_full_books'][0]==first


def test_states_are_explicit():
    now=[1000];s=StreamBook('m','c',('1','2'),5000,clock=lambda:now[0])
    assert s.read()['state']=='DISCONNECTED'
    s.connected_generation();assert s.read()['state']=='CONNECTED'
    s.ingest(event());assert s.read()['state']=='INITIAL_SNAPSHOT_PENDING'
    s.ingest(event('2'));assert s.read()['state']=='SYNCHRONIZED'
    now[0]=1501;assert s.read()['state']=='STALE'
    s.disconnect();assert s.read()['state']=='DISCONNECTED'


def test_cursor_missing_never_falls_back_to_genesis(tmp_path):
    import analysis.qualify_post_genesis as q
    with pytest.raises(ValueError,match='INVENTORY_CURSOR_REQUIRED'):
        q.load_inventory_cursor(tmp_path,{'snapshot_sha256':'g'})


def test_seed_empty_scoped_cursor_from_existing_report(tmp_path):
    import analysis.qualify_post_genesis as q
    prior={'snapshot_sha256':'g','snapshot':{'block_number':10}}
    r={'genesis_snapshot_sha256':'g','genesis_unchanged':True,'network_mode':'MANUAL_TARGET',
       'inventory_incremental':{'from_block':11,'to_block':20,'block_hash':'0x'+'a'*64,
           'events_count':0,'assets_checked':0,'observed_ms':1,'provenance':'POST_GENESIS_CTF_INCOMING_EVENTS_AND_ANCHORED_BALANCES'}}
    (tmp_path/'D6_POST_GENESIS_READINESS_fixture.json').write_text(json.dumps(r))
    x=q.load_inventory_cursor(tmp_path,prior)
    assert x['to_block']==20 and x['observed_ms']==1 and x['balances']=={}


def test_fixed_tail_never_refetches_or_rescans_genesis(monkeypatch):
    import analysis.qualify_post_genesis as q
    calls=[]
    class RPC:
        def call(self,m,p):
            calls.append((m,p))
            if p[0]=='0x14':return {'hash':'cursor'}
            assert p[0]=='latest'
            return {'number':'0x16','hash':'target','timestamp':'0x1'}
    def scan(rpc,start,end,known,*,capture):
        assert (start,end)==(21,22);capture['balances']={}
        return {'status':'PASS_SCOPED_READS','block_hash':'target','to_block':end,'events_count':0}
    monkeypatch.setattr(q,'scan_ctf',scan)
    old={'from_block':11,'to_block':20,'block_hash':'cursor','balances':{},'events_count':0,'observed_ms':1}
    r=q.advance_inventory(RPC(),{'snapshot':{'block_number':10}},old)
    assert r['to_block']==22 and old['to_block']==20
    assert len(calls)==2


def test_cursor_atomic_roundtrip_and_tamper(tmp_path):
    import analysis.qualify_post_genesis as q
    prior={'snapshot_sha256':'g','snapshot':{'block_number':10}}
    x={'status':'PASS_SCOPED_READS','from_block':11,'to_block':20,'block_hash':'0x'+'a'*64,'balances':{},'events_count':0,'assets_checked':0,'observed_ms':1}
    q.save_inventory_cursor(tmp_path,prior,x)
    assert q.load_inventory_cursor(tmp_path,prior)==x
    assert not list((tmp_path/'runtime/d6_inventory_cursors').glob('*.tmp'))
    f=next((tmp_path/'runtime/d6_inventory_cursors').glob('*.json'))
    r=json.loads(f.read_text());r['inventory_incremental']['to_block']=21;f.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='CURSOR_INTEGRITY'):q.load_inventory_cursor(tmp_path,prior)


def test_wire_sides_and_token_mapping_never_cross_fill():
    s=StreamBook('m','c',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    s.ingest(event(asks=[]))
    x=event('2');x['bids']=[]
    s.ingest(x)
    r=s.read();assert r['state']=='SYNCHRONIZED' and not r['available']
    assert [x['token_index'] for x in r['diagnostics']['first_full_books']]==[0,1]
    assert r['diagnostics']['resync_complete_generation']==1
    assert not r['market_eligible'] and r['reason']=='EMPTY_BOOK'


def test_pre_snapshot_delta_is_not_applied():
    s=StreamBook('m','c',('1','2'),5000,clock=lambda:1000);s.connected_generation()
    s.ingest({'event_type':'price_change','market':'c','timestamp':'1000','price_changes':[{'asset_id':'1','side':'BUY','price':'.5','size':'2'}]})
    assert s.depth=={} and s.read()['state']=='INITIAL_SNAPSHOT_PENDING'
