import asyncio,types
import pytest
from .observation_timing import TimedTransport,timed_stage,finish_observation
from .bound_diagnostics import read_positions,wire_projection
from .test_bound_diagnostics import position,position_page,checks

class Clock:
    def __init__(self):self.ms=100000
    def __call__(self):return self.ms
class Slow:
    def __init__(self,clock,responses,delays):self.clock=clock;self.responses=responses;self.delays=delays;self.n=0
    async def get_json(self,path,params=None):
        i=self.n;self.n+=1;self.clock.ms+=self.delays[i];return self.responses[i]

def test_slow_balance_cannot_become_fresh_at_completion():
    clock=Clock();t=TimedTransport(Slow(clock,[{'balance':'1'}],[6001]),clock)
    async def op():await t.get_json('/balance-allowance');return {'status':'AVAILABLE_SCOPED'}
    r=asyncio.run(timed_stage(op,[t],clock=clock))
    assert r['status']=='UNAVAILABLE' and r['reason']=='OLDEST_OBSERVATION_STALE'
    assert r['observed_ms']==100000 and r['valid_until_ms']==105000 and r['read_interval_ms']['end']==106001
    assert r['page_timestamps'][0]['receive_ms']==106001

def test_early_position_page_not_rejuvenated_by_slow_later_page():
    c=Clock();t=TimedTransport(Slow(c,[position_page([position()],True,'x'),position_page([{**position(),'token_id':'456'}])],[1,6000]),c)
    r=asyncio.run(timed_stage(lambda:read_positions(t),[t],clock=c))
    assert r['status']=='UNAVAILABLE' and r['rows'] is None and r['count'] is None
    assert [p['read_start_ms'] for p in r['page_timestamps']]==[100000,100001]

def test_producer_timestamp_is_preserved_not_overwritten():
    r=finish_observation({'status':'AVAILABLE_SCOPED','observed_ms':96000},100000,100100,[])
    assert r['observed_ms']==96000 and r['freshness_anchor_ms']==96000 and r['valid_until_ms']==101000
    r=finish_observation({'status':'AVAILABLE_SCOPED','observed_ms':100050},100000,100100,[])
    assert r['observed_ms']==100050 and r['freshness_anchor_ms']==100000

def test_page_source_time_controls_oldest_anchor():
    c=Clock();t=TimedTransport(Slow(c,[{'observed_ms':90000}],[1]),c)
    async def op():await t.get_json('/page');return {'status':'AVAILABLE_SCOPED'}
    r=asyncio.run(timed_stage(op,[t],clock=c))
    assert r['status']=='UNAVAILABLE' and r['page_timestamps'][0]['producer_timestamps']=={'observed_ms':90000}
    assert r['freshness_anchor_ms']==90000

@pytest.mark.parametrize('stamp',[True,None,100101])
def test_invalid_or_future_source_timestamp_blocks(stamp):
    r=finish_observation({'status':'AVAILABLE_SCOPED','observed_ms':stamp},100000,100100,[])
    assert r['status']=='UNAVAILABLE' and r['observed_ms']==stamp

def test_crossing_expiry_rejected_even_with_fresh_page():
    c=Clock();t=TimedTransport(Slow(c,[{}],[2]),c)
    async def op():await t.get_json('/x');return {'status':'AVAILABLE_SCOPED'}
    r=asyncio.run(timed_stage(op,[t],clock=c,expiry_ms=100001))
    assert r['reason']=='MARKET_EXPIRED_DURING_OBSERVATION'

def test_projection_uses_oldest_anchor_not_new_producer_label():
    data=checks(106000);data['balance']['freshness_anchor_ms']=100000
    with pytest.raises(ValueError):asyncio.run(wire_projection(data,clock=lambda:106000).snapshot())

def test_legacy_end_only_timestamp_is_not_accepted_by_new_projection():
    data=checks(100000)
    for row in data.values():row.pop('timing_schema');row.pop('freshness_anchor_ms')
    with pytest.raises(ValueError):asyncio.run(wire_projection(data,clock=lambda:100000).snapshot())

@pytest.mark.parametrize('delay,near_expiry',[(6001,False),(2000,True)])
def test_adapter_rejects_slow_balance_or_crossing_expiry(monkeypatch,delay,near_expiry):
    import time
    from .bound_diagnostics import BoundObservationAdapter
    from .compare_accounts import D6,EOA
    from .identify_account import CONTRACT
    from app.live.network_readonly import ReadOnlyClient
    from app.collectors.polymarket import PolymarketMarketDiscovery
    c=Clock();start=int(time.time())//300*300;c.ms=start*1000+(299500 if near_expiry else 100000)
    calls=[]
    class Fake:
        observations=[]
        async def get_json(self,path,params=None):
            calls.append(path);c.ms+=delay if path=='/balance-allowance' else 1
            if path=='/time':return c.ms//1000
            if path=='/markets':return [{'active':True,'closed':False}]
            if path=='/balance-allowance':return {'balance':'1'}
            if path in ('/data/orders','/data/trades'):return {'data':[],'next_cursor':'LTE=','count':0,'limit':100}
            if path=='/v2/positions':return position_page([])
            return {'data':{}}
    f=Fake();client=ReadOnlyClient(wallet=D6,signature_type=3,clob=f,data=f)
    market={'market_key':'5m','slug':'btc-updown-5m-'+str(start),'token_ids':{'UP':'123','DOWN':'456'},'expiry_ts_ms':(start+300)*1000,'metadata':{'conditionId':'0x'+'a'*64,'outcomes':['Up','Down']}}
    monkeypatch.setattr(PolymarketMarketDiscovery,'parse_market_list',lambda rows:[market])
    binding={'identity_only':True,'account':D6,'signer':EOA,'signature_type':3,'collateral_contract':CONTRACT}
    r=asyncio.run(BoundObservationAdapter(binding,client,f,f,clock=c).observe())
    assert r['checks']['balance']['status']=='UNAVAILABLE' and r['account_adapter_projection']['status']=='UNAVAILABLE'
    if near_expiry:assert calls==['/time','/markets','/balance-allowance']
