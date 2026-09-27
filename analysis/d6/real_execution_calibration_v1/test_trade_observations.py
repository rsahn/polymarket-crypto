import asyncio,copy,types
import pytest
from .observed_trades import validate_trade,TradeScopeError,collect_scoped_trades
from .observation_collector import Collector,ReadBudget

ACCOUNT='0x'+'1'*40
OTHER='0x'+'2'*40
MARKET='0x'+'a'*64
TX='0x'+'b'*64
START=1790509500
NOW=(START+20)*1000
TOKENS=('123','456')

def trade(role='TAKER',tid='trade-1'):
    maker=dict(order_id='maker-order',asset_id='123',maker_address=OTHER if role=='TAKER' else ACCOUNT,owner='fixture-owner',side='SELL',price='0.5',matched_amount='2',outcome='Up',fee_rate_bps='0')
    return dict(id=tid,market=MARKET,asset_id='123',maker_address=ACCOUNT if role=='TAKER' else OTHER,owner='fixture-owner',trader_side=role,taker_order_id='taker-order',side='BUY',price='0.5',size='2',status='CONFIRMED',fee_rate_bps='0',bucket_index=0,outcome='Up',match_time=str(START+1),last_update=str(START+2),transaction_hash=TX,maker_orders=[maker])

def validate(raw):return validate_trade(raw,account=ACCOUNT,market=MARKET,tokens=TOKENS,start_seconds=START,expiry_ms=(START+300)*1000,received_ms=NOW)

class Client:
    def __init__(self,pages):
        self.pages=pages;self.wallet=ACCOUNT;self.signature_type=0;self.clob=types.SimpleNamespace(observations=[]);self.data=object()
    def _pages(self,build,parse):
        path,params=build()
        if path=='/data/trades':
            assert params['market']==MARKET and params['after']==str(START)
            sources=self.pages
        else:sources=[[]]
        owner=self
        class Pages:
            def __init__(self,index=0):self.index=index
            async def first_page(self):
                payload={'data':copy.deepcopy(sources[self.index]),'next_cursor':'LTE=' if self.index==len(sources)-1 else 'MQ=='}
                owner.clob.observations.append(dict(endpoint='https://clob.polymarket.com'+path,response_digest='c'*64))
                return parse(payload)
            def from_cursor(self,cursor):return Pages(self.index+1)
        return Pages()
    async def get_balance_allowance(self,**kw):
        from polymarket._internal.environment import PRODUCTION_CONFIG as env
        self.clob.observations.append(dict(endpoint='https://clob.polymarket.com/balance-allowance',response_digest='d'*64))
        return {'balance':'0','allowances':{env.standard_exchange:'0'}}
    def list_positions(self,**kw):
        class Empty:
            async def first_page(self):return types.SimpleNamespace(items=[],has_more=False,next_cursor=None)
        return Empty()

def batch(pages):return asyncio.run(collect_scoped_trades(Client(pages),account=ACCOUNT,market=MARKET,tokens=TOKENS,start_seconds=START,expiry_ms=(START+300)*1000,clock=lambda:NOW))

@pytest.mark.parametrize('role',['MAKER','TAKER'])
def test_valid_attributed_wire_trade_and_sdk_page(role):
    raw=trade(role);r=validate(raw)
    assert r['order_id']==('maker-order' if role=='MAKER' else 'taker-order') and r['account']==ACCOUNT
    summary,rows=batch([[raw]])
    assert summary['status']=='OBSERVED_ATTRIBUTED' and summary['count']==1
    assert rows[0]['transaction_hash']==TX and summary['fee_effects_proven'] is False
    if role=='MAKER':
        raw['maker_address']=ACCOUNT
        assert validate(raw)['order_id']=='maker-order'  # top maker field is not an implied taker role

BAD=[('bucket_index',True),('owner',False),('outcome','UNKNOWN'),('market','0x'+'f'*64),('market',False),('match_time',str(START-1)),('match_time',str(START+301)),('match_time',str(START+21)),('match_time',True),('match_time',float(START+1)),('match_time',str((START+1)*1000)),('match_time','2026-09-27T11:45:01'),('match_time','2026-09-99T11:45:01Z'),('last_update',str(START)),('maker_address',OTHER),('maker_address',123),('trader_side','UNKNOWN'),('trader_side',None),('taker_order_id',''),('taker_order_id',True),('price',True),('price','NaN'),('price',0.5),('price','1'),('size','-1'),('size','Infinity'),('size',[]),('transaction_hash','secret=CANARY'),('transaction_hash',False),('transaction_hash',None),('status','UNKNOWN'),('asset_id','789'),('token_id','456'),('maker_orders',{}),('maker_orders',[])]
@pytest.mark.parametrize('field,value',BAD)
def test_invalid_wire_trade_blocks_whole_response(field,value):
    raw=trade();raw[field]=value
    with pytest.raises(TradeScopeError):validate(raw)
    summary,rows=batch([[trade(tid='valid-before-invalid'),raw]])
    assert summary['status']=='BLOCKED' and summary['count'] is None and rows==[]
    assert summary['receipt_candidates_allowed'] is False and 'status_counts' not in summary
    assert summary['provenance']['response_digests']==['c'*64]
    assert 'CANARY' not in str(summary)

@pytest.mark.parametrize('mutation',['both_roles','two_own_makers','duplicate_order','foreign_maker','missing_field','bool_quantity'])
def test_ambiguous_or_malformed_maker_attribution(mutation):
    raw=trade('MAKER')
    if mutation=='both_roles':raw['taker_address']=ACCOUNT
    if mutation=='two_own_makers':raw['maker_orders'].append({**raw['maker_orders'][0],'order_id':'another'})
    if mutation=='duplicate_order':raw['maker_orders'][0]['order_id']=raw['taker_order_id']
    if mutation=='foreign_maker':raw['maker_orders'][0]['maker_address']=OTHER
    if mutation=='missing_field':del raw['maker_orders'][0]['order_id']
    if mutation=='bool_quantity':raw['maker_orders'][0]['matched_amount']=True
    with pytest.raises(TradeScopeError):validate(raw)
    assert batch([[raw]])[0]['status']=='BLOCKED'

def test_later_bad_page_discards_previously_valid_candidates():
    invalid=trade(tid='bad-page');invalid['market']='0x'+'f'*64
    summary,rows=batch([[trade()],[invalid]])
    assert summary['status']=='BLOCKED' and summary['failed_row_index']==1 and rows==[] and summary['count'] is None

def test_duplicate_trade_across_pages_is_blocked():
    summary,rows=batch([[trade()],[trade()]])
    assert summary['reason']=='TRADE_DUPLICATE_ID' and rows==[]

def test_aware_iso_timestamp_and_pending_trade_no_candidate():
    raw=trade();raw['match_time']='2026-09-27T11:45:01Z';raw['last_update']='2026-09-27T13:45:02+02:00'
    assert validate(raw)['matched_us']==(START+1)*1000000
    raw['status']='MATCHED';raw['transaction_hash']=''
    assert validate(raw)['transaction_hash'] is None

@pytest.mark.parametrize('role',['MAKER','TAKER','INVALID'])
def test_collector_only_exposes_attributed_candidates_and_invalid_cannot_reach_rpc(monkeypatch,role):
    raw=trade('MAKER' if role=='MAKER' else 'TAKER')
    if role=='INVALID':raw['maker_address']=OTHER
    client=Client([[raw]])
    class Public:
        async def get_json(self,path,params=None):return NOW//1000 if path=='/time' else {'base_fee':1000}
    class Gamma:
        async def get_json(self,*a,**kw):return [{'active':True,'closed':False}]
    from app.collectors.polymarket import PolymarketMarketDiscovery
    parsed=dict(market_key='5m',slug='btc-updown-5m-'+str(START),token_ids={'UP':'123','DOWN':'456'},expiry_ts_ms=(START+300)*1000,metadata={'conditionId':MARKET,'outcomes':['Up','Down']})
    monkeypatch.setattr(PolymarketMarketDiscovery,'parse_market_list',lambda rows:[parsed])
    c=Collector(client,Public(),Gamma(),wallet=ACCOUNT,signer=ACCOUNT,signature_type=0,budget=ReadBudget(),clock=lambda:NOW)
    r=asyncio.run(c.collect({'selectors':{},'market_policy':'OFFLINE_FIXTURE'}))
    if role!='INVALID':assert r['receipt_candidates']==[TX]
    else:
        assert r['checks']['trades']['status']=='BLOCKED' and r['receipt_candidates']==[]
        from .chain_observer import ReceiptRPC
        rpc=ReceiptRPC(ACCOUNT,receipt_ids=r['receipt_candidates'])
        with pytest.raises(ValueError,match='NOT_OBSERVED'):rpc.call('eth_getTransactionReceipt',[TX])
        assert rpc.calls==[] and rpc.counter==0

def test_taker_with_own_maker_leg_is_ambiguous():
    raw=trade();raw['maker_orders'][0]['maker_address']=ACCOUNT
    summary,rows=batch([[raw]])
    assert summary['reason']=='TRADE_AMBIGUOUS_ROLE' and rows==[]

def test_bad_later_page_does_not_blame_previously_valid_row():
    summary,rows=batch([[trade()],None])
    assert summary['status']=='BLOCKED' and summary['reason']=='TRADE_PAGE_SCHEMA'
    assert summary['failed_row_index'] is None and summary['count'] is None and rows==[]
