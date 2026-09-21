import importlib.util
from pathlib import Path
P=Path(__file__).parent

def load(name):
    spec=importlib.util.spec_from_file_location(name,P/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.PolymarketOrderbookCollector('5m',{'UP':'u','DOWN':'d'},None,timestamp_contract='D5.1')

def book(token,ts):
    return {'event_type':'book','asset_id':token,'timestamp':ts,'bids':[{'price':'.4','size':'2'}],'asks':[{'price':'.6','size':'3'}]}

def test_projection_invalidation_and_snapshot_isolation():
    a,b=load('reference'),load('candidate')
    initial=[book('u',100),book('d',100)]
    x=a.normalize_snapshot(initial,101);y=b.normalize_snapshot(initial,101);assert x==y
    x['up']['bids'].clear();y['up']['bids'].clear()
    payloads=[
      {'event_type':'last_trade_price','asset_id':'u','timestamp':102,'price':'.5'},
      {'event_type':'price_change','timestamp':103,'price_changes':[{'asset_id':'u','side':'BUY','price':'.45','size':'7','best_bid':'.45','best_ask':'.6'}]},
      book('d',104),
      {'event_type':'price_change','timestamp':105,'price_changes':[{'asset_id':'d','side':'SELL','price':'.6','size':'0','best_bid':'.4','best_ask':'.7'}]},
      {'event_type':'last_trade_price','asset_id':'u','timestamp':99,'price':'.5'},
    ]
    for j,payload in enumerate(payloads):
        assert a.normalize_snapshot(payload,110+j)==b.normalize_snapshot(payload,110+j)
    assert len(b._projection_cache)<=2
    a._reset_connection_state();b._reset_connection_state();assert b._projection_cache=={}
    assert a.normalize_snapshot(initial,120)==b.normalize_snapshot(initial,120)
