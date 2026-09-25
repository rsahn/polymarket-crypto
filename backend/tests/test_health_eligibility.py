import asyncio
import pytest
from app.live.readonly_book_stream import StreamBook
from app.live.readiness import ProductionReadinessCheck
from app.live.forward_readiness import ObservationSource


def event(t,empty=False):
    return dict(event_type="book",market="c",asset_id=t,timestamp="1000",bids=[dict(price=".4",size="1")],asks=[] if empty else [dict(price=".6",size="1")])


def test_empty_snapshot_is_synced_but_not_eligible_and_stales():
    now=[1000];s=StreamBook("m","c",("a","b"),5000,clock=lambda:now[0]);s.connected_generation()
    s.ingest(event("a",True));s.ingest(event("b",True));r=s.read()
    assert r["connected"] and r["synchronized"] and r["fresh"]
    assert r["reason"]=="EMPTY_BOOK" and not r["market_eligible"] and not r["available"]
    assert s.depth["a"]["asks"]=={} and r["state"]=="SYNCHRONIZED"
    now[0]=1501;assert not s.read()["fresh"]


def test_health_true_empty_market_false_never_submit():
    s=StreamBook("m","c",("a","b"),5000,clock=lambda:1000);s.connected_generation()
    s.ingest(event("a",True));s.ingest(event("b"))
    src=lambda **k:ObservationSource(dict(available=True,observed_ms=1000,**k))
    r=asyncio.run(ProductionReadinessCheck(account=src(authenticated=True,balance_usdc="100",allowance_usdc="100",complete=True,open_order_ids=[]),
        positions=src(complete=True,balances={}),book=s,geo=src(blocked=False),risk=src(allow=True),
        local_reader=lambda:{"phase":"CLOSED"},clock=lambda:1000).run())
    assert r["SYSTEM_READY"] and not r["MARKET_ELIGIBLE_NOW"]
    assert r["operating_state"]=="NO_TRADE" and not r["submit_allowed"] and not r["ready_for_arm"]


def test_crossed_remains_invalid():
    s=StreamBook("m","c",("a","b"),5000,clock=lambda:1000);s.connected_generation()
    e=event("a");e["asks"][0]["price"]=".3"
    with pytest.raises(ValueError,match="CROSSED_BOOK"):s.ingest(e)
    assert not s.read().get("market_eligible",False) and not s.read()["synchronized"]


def test_finalized_positive_skew_is_metadata_not_freshness(monkeypatch):
    import analysis.qualify_post_b_proofs as q
    monkeypatch.setattr(q,"now_ms",lambda:1718)
    class R:
        def call(self,m,p):
            return "0x89" if m=="eth_chainId" else dict(number="0x16",hash="0x"+"a"*64,timestamp="0x2")
    d={};r=q.qualify_finalized(R(),diagnostics=d)
    assert r["status"]=="PASS_PROVIDER_FINALIZED_READ"
    assert d["reads"][0]["block_minus_receive_ms"]==282
    assert d["clock_source"]=="LOCAL_TIME_TIME_NS_UTC"
    assert d["clock_accuracy_proven"] is False


@pytest.mark.parametrize('scan_time,reason',[(100,'GENERATION_STALE_500MS'),(900,'POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN')])
def test_post_b_preserves_original_scan_time(monkeypatch,scan_time,reason):
    import analysis.qualify_post_b_proofs as q
    import analysis.qualify_post_genesis as runner
    monkeypatch.setattr(q,"now_ms",lambda:1000)
    calls=[]
    class RPC:
        def call(self,m,p):
            calls.append(p[0])
            return dict(number="0x16" if p[0]=="0x16" else "0x18",hash="0x"+("a" if p[0]=="0x16" else "b")*64,timestamp="0x1")
    async def views(client):return {k:([],1000) for k in ("balance","orders","trades","positions")}
    class Geo:
        async def read(self):return {"available":True}
    tail=dict(to_block=24,block_hash="0x"+"b"*64,balances={},events_count=0,observed_ms=scan_time,assets_checked=0)
    monkeypatch.setattr(q,"fixed_scan",lambda *a:(dict(tail),[[23,24]]))
    monkeypatch.setattr(runner,"fresh_views",views)
    prior={"from_block":11,"to_block":22,"cursor_previous":20,"anchor_catchup_ranges":[[21,22]]}
    qualified={"status":"PASS_PROVIDER_FINALIZED_READ","anchor":dict(number=22,hash="0x"+"a"*64)}
    obs,geo,inv=asyncio.run(q.acquire_post_b(None,Geo(),RPC(),prior,qualified))
    assert not inv["post_b_proof"]["current_inventory_proven"]
    assert inv["post_b_proof"]["reason"]==reason
    assert inv["observed_ms"]==scan_time and inv["scan_observed_ms"]==scan_time
    assert calls==["latest","0x18","0x18","0x16"] and len(obs)==4
