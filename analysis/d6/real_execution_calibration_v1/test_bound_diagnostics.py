import asyncio,copy,json,time,types
from pathlib import Path
import pytest
from .binding_consumer import envelope,consume,legacy_identity,SCOPE
from .bound_diagnostics import read_orders,read_positions,wire_projection,BoundObservationAdapter
from .compare_accounts import EOA,D6
from .identify_account import CONTRACT
from .core import digest
from .v1_binding import verify

@pytest.fixture
def binding_files(tmp_path):
    stamp=int(time.time()*1000)-1000000
    block={'number':1,'number_hex':'0x1','hash':'0x'+'a'*64,'timestamp_ms':stamp-1000}
    source={'mode':'AUTHORIZED_PINNED_CASH_ACCOUNT_IDENTIFICATION','submit_allowed':False,'before':{EOA:'0',D6:'1'},'after':{EOA:'0',D6:'1'},'identity':{'artifact_identity_confirmed':True,'genesis_identity_confirmed':True,'strategy_hashes':verify()},'chain':{'status':'PINNED_CASH_OBSERVED','chain_id':137,'contract':CONTRACT,'symbol':'pUSD','decimals':6,'block_hash_rechecked':True,'block':block,'balances_raw':{EOA:'0',D6:'1'}},'finished_ms':stamp,'verdict':{'status':'ACCOUNT_IDENTIFIED','reconciliation_account':D6,'calibration_ready':False,'submit_allowed':False},'explicit_context':{'reconciliation_account':D6,'signer':EOA,'signature_type':3}}
    b={'status':'ACCOUNT_IDENTIFIED','source_evidence':'evidence.json','source_digest':digest(source),'scope':SCOPE,'reconciliation_account':D6,'signer':EOA,'signature_type':3,'chain_id':137,'collateral_contract':CONTRACT,'calibration_ready':False,'submit_allowed':False,'automatic_startup_override':False,'block':block,'observed_ms':stamp,'cash_observation_valid_until_ms':stamp+5000}
    (tmp_path/'evidence.json').write_text(json.dumps(source));legacy=tmp_path/'binding.json';legacy.write_text(json.dumps(b))
    versioned=tmp_path/'binding_v1.json';versioned.write_text(json.dumps(envelope(legacy)))
    return legacy,versioned

def test_expired_cash_can_supply_identity_but_never_cash(binding_files):
    legacy,v=binding_files;r=consume(v,legacy)
    assert r['account']==D6 and r['signer']==EOA and r['signature_type']==3
    assert r['current_cash'] is None and r['cash_reacquisition_required'] and r['identity_only']

@pytest.mark.parametrize('field,value',[('schema_version',2),('schema_version',True),('schema','BAD'),('sdk_version','0.12.0'),('legacy_input_profile','UNKNOWN'),('automatic_override',True),('source_digest','f'*64),('legacy_binding_digest','f'*64),('role_scope','wallet')])
def test_versioned_binding_tampering_rejected(binding_files,field,value):
    legacy,v=binding_files;r=json.loads(v.read_text());r[field]=value;v.write_text(json.dumps(r))
    with pytest.raises(ValueError):consume(v,legacy)

@pytest.mark.parametrize('field,value',[('signer',D6),('reconciliation_account',EOA),('signature_type',0),('signature_type',True),('chain_id',1),('collateral_contract','0x'+'f'*40),('scope','cash'),('submit_allowed',True),('source_evidence','../secret.json'),('schema_version',2)])
def test_legacy_binding_role_scope_version_not_overridden(binding_files,field,value):
    legacy,v=binding_files;r=json.loads(legacy.read_text());r[field]=value;legacy.write_text(json.dumps(r))
    with pytest.raises(ValueError):envelope(legacy)

def test_source_digest_tampering_rejected(binding_files):
    legacy,v=binding_files;p=legacy.parent/'evidence.json';r=json.loads(p.read_text());r['before'][D6]='2';p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='DIGEST'):consume(v,legacy)

class Transport:
    def __init__(self,payloads):self.payloads=payloads;self.calls=[]
    async def get_json(self,path,params=None):
        self.calls.append((path,params));return copy.deepcopy(self.payloads[len(self.calls)-1])

def order():return dict(id='order',maker_address=D6,asset_id='123',market='0x'+'a'*64,side='BUY',status='LIVE',created_at=int(time.time())-1,price='0.5',original_size='2',size_matched='0',owner='fixture-owner',outcome='Up',expiration='0',order_type='GTC',associate_trades=[])
def order_page(rows):return {'data':rows,'next_cursor':'LTE=','limit':100,'count':len(rows)}
def position():return dict(proxy_wallet=D6,token_id='123',condition_id='0x'+'a'*64,current_size=2,status='OPEN')
def position_page(rows,more=False,cursor=None):return {'data':rows,'pagination':{'has_more':more,'next_cursor':cursor}}

def test_valid_raw_readers_keep_scopes_and_pagination_distinct():
    o=asyncio.run(read_orders(Transport([order_page([order()])])))
    p=asyncio.run(read_positions(Transport([position_page([position()])])))
    assert o['count']==p['count']==1 and o['wallet_complete'] is None and p['account_state_asof'] is None

@pytest.mark.parametrize('change',[{'maker_address':EOA},{'created_at':True},{'original_size':True},{'size_matched':'3'},{'status':'FILLED'},{'token_id':'456'},{'market':'bad'},{'price':'NaN'}])
def test_foreign_ambiguous_or_coerced_order_rejected(change):
    with pytest.raises(ValueError):asyncio.run(read_orders(Transport([order_page([{**order(),**change}])])))

@pytest.mark.parametrize('change',[{'proxy_wallet':EOA},{'current_size':True},{'current_size':float('nan')},{'status':'UNKNOWN'},{'token_id':False},{'condition_id':'bad'}])
def test_foreign_or_malformed_position_rejected(change):
    with pytest.raises(ValueError):asyncio.run(read_positions(Transport([position_page([{**position(),**change}])])))

def test_position_pagination_is_bounded_not_complete():
    rows=[{**position(),'token_id':str(i)} for i in range(1,51)]
    rows2=[{**position(),'token_id':str(i)} for i in range(51,101)]
    t=Transport([position_page(rows,True,'one'),position_page(rows2,True,'two')]);r=asyncio.run(read_positions(t))
    assert len(t.calls)==2 and r['count']==100 and not r['pagination_complete'] and r['wallet_complete'] is None

def test_later_foreign_position_discards_whole_operation():
    t=Transport([position_page([position()],True,'one'),position_page([{**position(),'proxy_wallet':EOA,'token_id':'456'}])])
    with pytest.raises(ValueError):asyncio.run(read_positions(t))

def checks(stamp):
    data={'balance':{'status':'AVAILABLE_SCOPED','observed_ms':stamp,'balance_pusd':'109.16'},'orders':{'status':'AVAILABLE_SCOPED','observed_ms':stamp,'rows':[],'scope':'credential'},'trades':{'status':'OBSERVED_ATTRIBUTED','observed_ms':stamp,'rows':[],'scope':'market_window'},'positions':{'status':'AVAILABLE_SCOPED_INDEX','observed_ms':stamp,'rows':[],'scope':'address_index'}}
    for row in data.values():row.update(timing_schema='READ_INTERVALS_OLDEST_ANCHOR/1',freshness_anchor_ms=stamp)
    return data

def test_real_account_adapter_projection_is_partial_and_expires_without_network():
    stamp=int(time.time()*1000);c=checks(stamp)
    r=asyncio.run(wire_projection(c,clock=lambda:stamp).snapshot())
    assert r['account']==D6 and r['cash']=='109.16' and r['positions']=={}
    assert not r['inventory_proven'] and not r['orders_complete'] and not r['positions_complete']
    with pytest.raises(ValueError):asyncio.run(wire_projection(c,clock=lambda:stamp+5001).snapshot())
    c['orders']={'status':'UNAVAILABLE'}
    with pytest.raises(ValueError):asyncio.run(wire_projection(c,clock=lambda:stamp).snapshot())

def test_adapter_context_changes_and_reuse_are_rejected():
    binding={'identity_only':True,'account':D6,'signer':EOA,'signature_type':3};client=types.SimpleNamespace(wallet=D6,signature_type=3,clob=object(),data=object())
    a=BoundObservationAdapter(binding,client,object(),object());client.signature_type=0
    with pytest.raises(ValueError,match='CONTEXT'):asyncio.run(a.observe())
    client.signature_type=3;a.used=True
    with pytest.raises(ValueError,match='ONE_SHOT'):asyncio.run(a.observe())

def test_real_readonly_client_to_existing_account_adapter_without_network(monkeypatch,binding_files):
    from app.live.network_readonly import ReadOnlyClient
    from app.collectors.polymarket import PolymarketMarketDiscovery
    legacy,v=binding_files;binding=consume(v,legacy);now=int(time.time());start=now//300*300
    class Fake:
        def __init__(self):self.observations=[];self.calls=[]
        async def get_json(self,path,params=None):
            self.calls.append((path,params))
            self.observations.append({'endpoint':'https://clob.polymarket.com'+path,'response_digest':'a'*64})
            if path=='/time':return int(time.time())
            if path=='/markets':return [{'active':True,'closed':False}]
            if path=='/balance-allowance':
                assert params['signature_type']==3
                return {'balance':'109160000','allowances':{'ignored':'UNQUALIFIED'}}
            if path in ('/data/orders','/data/trades'):return order_page([])
            if path=='/v2/status':return {'data':{'computed_at':'2026-09-27T13:00:00Z'}}
            assert path=='/v2/positions' and params['user']==D6
            return position_page([])
    f=Fake();client=ReadOnlyClient(wallet=D6,signature_type=3,clob=f,data=f)
    parsed={'market_key':'5m','slug':'btc-updown-5m-'+str(start),'token_ids':{'UP':'123','DOWN':'456'},'expiry_ts_ms':(start+300)*1000,'metadata':{'conditionId':'0x'+'a'*64,'outcomes':['Up','Down']}}
    monkeypatch.setattr(PolymarketMarketDiscovery,'parse_market_list',lambda rows:[parsed])
    r=asyncio.run(BoundObservationAdapter(binding,client,f,f).observe())
    assert len(f.calls)==7
    assert r['account_adapter_projection']['status']=='AVAILABLE_DIAGNOSTIC_NOT_EXECUTION'
    assert r['account_adapter_projection']['snapshot']['cash']=='109.16'
    assert r['checks']['positions']['wallet_complete'] is None and not r['submit_allowed']
    assert r['binding']['current_cash'] is None and not r['cash_from_historical_binding_used']

def test_maker_reported_quantity_not_taker_aggregate_and_no_invented_fees():
    from .test_trade_observations import trade,validate,OTHER
    raw=trade('MAKER');raw['maker_orders'][0]['matched_amount']='1'
    raw['maker_orders'].append({**raw['maker_orders'][0],'order_id':'other','maker_address':OTHER})
    row=validate(raw)
    assert row['shares']=='1' and row['price']=='0.5' and row['cash_fee'] is None and row['share_fee'] is None

@pytest.mark.parametrize('change',[{'wallet':EOA},{'signer':D6},{'balance':True},{'balance':109},{'signature_type':True},{'signature_type':0},{'collateral_contract':EOA},{'asset_type':'CONDITIONAL'}])
def test_balance_raw_contradictions_are_blocked_without_required_echo(change):
    from .bound_diagnostics import validate_balance
    with pytest.raises(ValueError):validate_balance({'balance':'109160000',**change},{'collateral_contract':CONTRACT})

def test_balance_does_not_require_echo_or_inspect_allowances():
    from .bound_diagnostics import validate_balance
    r=validate_balance({'balance':'109160000','allowances':'NOT_INTERPRETED'},{'collateral_contract':CONTRACT})
    assert r['balance_pusd']=='109.16' and r['cash_state_block'] is None
