import copy
import pytest
from app.live.readonly_book_stream import StreamBook

S=1790348236333

def book(token="a",stamp=S):
    return dict(event_type="book",market="c",asset_id=token,timestamp=str(stamp),
        bids=[dict(price=".4",size="2")],asks=[dict(price=".6",size="2")])


def delta(stamp=S-16,token="a"):
    return dict(event_type="price_change",market="c",timestamp=str(stamp),
        price_changes=[dict(asset_id=token,side="BUY",price=".45",size="3")])


def stream():
    s=StreamBook("m","c",("a","b"),S+10000,clock=lambda:S+80)
    s.connected_generation();s.ingest(book());s.ingest(book("b"));return s


@pytest.mark.parametrize("offset",[2,15,16])
def test_exact_observed_pre_snapshot_delta_never_reaches_mutation_or_update(monkeypatch,offset):
    s=stream();before=copy.deepcopy(s.depth)
    calls=[]
    original=s.update
    def watch(*a,**kw):
        calls.append(copy.deepcopy(s.depth));return original(*a,**kw)
    monkeypatch.setattr(s,"update",watch)
    with pytest.raises(ValueError,match="^BOOK_REGRESSION$"):s.ingest(delta(S-offset))
    assert calls==[]
    d=s.read()["diagnostics"]["regression_event"]
    assert d["delta_ms"]==-offset and d["reference_full_book_ms"]==S
    assert d["accepted_deltas_since_full_book"]==0
    assert d["classification"]=="PRE_SNAPSHOT_DELTA_SUPERSESSION_UNPROVEN"
    assert d["supersession_proven"] is False and not s.read()["available"]


def test_regression_after_accepted_delta_cannot_be_pre_snapshot_exception():
    s=stream();s.ingest(delta(S+1))
    with pytest.raises(ValueError):s.ingest(delta())
    d=s.read()["diagnostics"]["regression_event"]
    assert d["accepted_deltas_since_full_book"]==1
    assert d["classification"]=="REGRESSION_AFTER_ACCEPTED_DELTA"


@pytest.mark.parametrize("event",[book(stamp=S-1),delta(token="other"),{**delta(),"market":"other"}])
def test_full_book_or_identity_regressions_fail_closed(event):
    s=stream()
    with pytest.raises(ValueError):s.ingest(event)
    assert not s.read()["available"]


def test_new_generation_does_not_reuse_snapshot_reference():
    s=stream();s.connected_generation();s.ingest(delta())
    assert not s.read()["available"] and s.read()["diagnostics"]["regression_event"] is None


def test_equal_timestamp_preserves_existing_nonregression_contract():
    s=stream();s.ingest(delta(S));assert s.read()["available"]


def test_finalized_later_head_is_compared_to_its_own_receipt(monkeypatch):
    import analysis.qualify_post_b_proofs as q
    clock=[1000];monkeypatch.setattr(q,"now_ms",lambda:clock[0])
    class RPC:
        def call(self,m,p):
            if m=="eth_chainId":return "0x89"
            clock[0]+=1000
            return dict(number="0x17" if p[0]=="latest" else "0x16",hash="0x"+("b" if p[0]=="latest" else "a")*64,
                timestamp="0x3" if p[0]=="latest" else "0x1")
    d={};r=q.qualify_finalized(RPC(),diagnostics=d)
    assert r["status"]=="PASS_PROVIDER_FINALIZED_READ"
    assert d["reason"]=="FINALIZED_QUALIFIED" and len(d["reads"])==4


def test_finalized_consensus_timestamp_is_explicit_diagnostic_metadata(monkeypatch):
    import analysis.qualify_post_b_proofs as q
    monkeypatch.setattr(q,"now_ms",lambda:1000)
    class RPC:
        def call(self,m,p):
            if m=="eth_chainId":return "0x89"
            return dict(number="0x16",hash="0x"+"a"*64,timestamp="0x2",extra="SECRET_SENTINEL")
    d={}
    assert q.qualify_finalized(RPC(),diagnostics=d)["status"]=="PASS_PROVIDER_FINALIZED_READ"
    assert d["reads"][0]["block_minus_receive_ms"]==1000
    assert d["clock_accuracy_proven"] is False
    assert "SECRET_SENTINEL" not in str(d)


def test_finalized_failure_never_runs_inventory(monkeypatch):
    import asyncio
    import analysis.qualify_post_b_proofs as q
    monkeypatch.setenv("POLYGON_ARCHIVE_RPC_URL","https://example.invalid")
    monkeypatch.setattr(q,"read_genesis",lambda p:{"last_hash":"same"})
    class RPC:
        calls=[]
        def __init__(self,*a,**kw):pass
        def call(self,*a):raise RuntimeError("SECRET_SENTINEL")
    monkeypatch.setattr(q,"PublicRPC",RPC)
    async def ws(audit):return {"state":"DISCONNECTED"}
    monkeypatch.setattr(q,"capture_ws",ws)
    def forbidden(*a):raise AssertionError("INVENTORY_MUST_NOT_RUN")
    monkeypatch.setattr(q,"public_inventory",forbidden)
    r=asyncio.run(q.run(True))
    assert r["finalized"]["status"]=="BLOCKED" and r["inventory"]["status"]=="NOT_RUN"
    assert "SECRET_SENTINEL" not in str(r) and not r["ready_for_arm"]


@pytest.mark.parametrize("stamp",[True,1790348236333.5,"1790348236333.5"])
def test_ambiguous_timestamp_is_not_coerced(stamp):
    s=stream();e=delta();e["timestamp"]=stamp
    with pytest.raises(ValueError,match="AMBIGUOUS_TIMESTAMP"):s.ingest(e)
    assert not s.read()["available"]


def test_multi_token_regression_preflight_prevents_partial_mutation(monkeypatch):
    s=stream()
    s.ingest(delta(S+1,"b"))
    e=delta(S);e["price_changes"].append(dict(asset_id="b",side="BUY",price=".46",size="3"))
    calls=[];monkeypatch.setattr(s,"update",lambda *a,**kw:calls.append(a))
    with pytest.raises(ValueError,match="BOOK_REGRESSION"):s.ingest(e)
    assert calls==[] and not s.read()["available"]


def test_finalized_only_never_starts_ws_or_inventory(monkeypatch):
    import asyncio
    import analysis.qualify_post_b_proofs as q
    monkeypatch.setenv("POLYGON_ARCHIVE_RPC_URL","https://example.invalid")
    monkeypatch.setattr(q,"read_genesis",lambda p:{"last_hash":"same"})
    class RPC:
        calls=[]
        def __init__(self,*a,**kw):pass
    monkeypatch.setattr(q,"PublicRPC",RPC)
    monkeypatch.setattr(q,"qualify_finalized",lambda *a,**kw:{"status":"PASS_PROVIDER_FINALIZED_READ"})
    def forbidden(*a):raise AssertionError("MUST_NOT_START")
    monkeypatch.setattr(q,"capture_ws",forbidden);monkeypatch.setattr(q,"public_inventory",forbidden)
    r=asyncio.run(q.run(True,finalized_only=True))
    assert r["book"]["status"]==r["inventory"]["status"]=="NOT_RUN"
    assert not r["ready_for_arm"] and not r["submit_allowed"]
