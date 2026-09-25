import copy
import hashlib
import json
import pytest
from app.live.readonly_book_stream import StreamBook


def book(token,stamp):
    return dict(event_type="book",market="c",asset_id=token,timestamp=str(stamp),
                bids=[dict(price=".4",size="2")],asks=[dict(price=".6",size="2")])


def stream():
    s=StreamBook("m","c",("TOKEN_A","TOKEN_B"),5000,clock=lambda:1071)
    s.connected_generation()
    return s


@pytest.mark.parametrize("kind",["book","price_change"])
def test_same_token_regression_has_exact_sanitized_evidence(kind,capsys):
    s=stream();s.ingest(book("TOKEN_A",1001));s.ingest(book("TOKEN_B",1001))
    e=book("TOKEN_A",1000) if kind=="book" else dict(event_type=kind,market="c",timestamp="1000",
        price_changes=[dict(asset_id="TOKEN_A",side="BUY",price=".4",size="3")])
    with pytest.raises(ValueError,match="^BOOK_REGRESSION$"):s.ingest(e)
    r=s.read();d=r["diagnostics"]["regression_event"]
    assert d==dict(event_type=kind,token_index=0,token_sha256=hashlib.sha256(b"TOKEN_A").hexdigest(),
        source_timestamp_ms=1000,previous_accepted_source_timestamp_ms=1001,
        received_timestamp_ms=1071,delta_ms=-1,generation=1,
        comparison="source_timestamp_ms < same_token_accepted_source_timestamp_ms",
        reason="BOOK_REGRESSION",watermark_scope="TOKEN_WITHIN_CONNECTION_GENERATION")
    assert not r["available"] and r["state"]=="INVALID_BOOK"
    assert "TOKEN_A" not in json.dumps(d)
    assert capsys.readouterr().out==""
    assert capsys.readouterr().err==""


def test_equal_timestamps_and_independent_token_watermarks():
    s=stream();s.ingest(book("TOKEN_A",1001));s.ingest(book("TOKEN_B",1000))
    s.ingest(book("TOKEN_B",1000));s.ingest(book("TOKEN_A",1001))
    assert s.read()["state"]=="SYNCHRONIZED"
    assert s.books["TOKEN_A"]["observed_ms"]==1001
    assert s.books["TOKEN_B"]["observed_ms"]==1000


def test_regression_diagnostic_survives_disconnect_and_resets_on_new_generation():
    s=stream();s.ingest(book("TOKEN_A",1001))
    with pytest.raises(ValueError):s.ingest(book("TOKEN_A",1000))
    d=s.read()["diagnostics"]["regression_event"]
    s.disconnect();assert s.read()["diagnostics"]["regression_event"]==d
    s.connected_generation();assert s.read()["diagnostics"]["regression_event"] is None
    assert not s.read()["available"]


def evidence():
    return dict(chain_id=137,selection_tag="finalized",generation=1,
        anchor=dict(number=22,hash="0x"+"a"*64),
        recheck=dict(number=22,hash="0x"+"a"*64),
        cursor=dict(number=20,hash="0x"+"b"*64,verified_hash="0x"+"b"*64),
        ranges=[[21,21],[22,22]],logs_complete=True,balances_at_anchor=True,
        inventory_generation=1,inventory_observed_ms=900,
        account_generation=1,account_complete=True,account_observed_ms=950,
        recheck_observed_ms=970,latest_number=23)


def evaluate(e,now=1000):
    from analysis.stable_bound_20260925.contract_model import evaluate_anchor
    return evaluate_anchor(e,now=now)


def test_new_head_does_not_invalidate_anchored_scope_but_never_proves_current_inventory():
    e=evidence();before=copy.deepcopy(e)
    r=evaluate(e)
    assert r["anchored_valid"] and not r["current_inventory_proven"]
    assert not r["ready_for_arm"] and not r["submit_allowed"]
    assert r["reason"]=="POST_ANCHOR_SCOPE_UNPROVEN"
    assert e==before
    e["latest_number"]=24;assert evaluate(e)["anchored_valid"]


@pytest.mark.parametrize("mutation,reason",[
    (lambda e:e["recheck"].update(hash="0x"+"c"*64),"ANCHOR_REORG"),
    (lambda e:e.update(ranges=[[22,22]]),"COVERAGE_GAP_OR_OVERLAP"),
    (lambda e:e.update(ranges=[[21,22],[22,22]]),"COVERAGE_GAP_OR_OVERLAP"),
    (lambda e:e.update(inventory_observed_ms=499),"GENERATION_STALE_500MS"),
    (lambda e:e.update(account_generation=2),"GENERATION_PARTIAL"),
    (lambda e:e.update(account_complete=False),"GENERATION_PARTIAL"),
    (lambda e:e.update(logs_complete=False),"ANCHOR_SCOPE_INCOMPLETE"),
    (lambda e:e.update(balances_at_anchor=False),"ANCHOR_SCOPE_INCOMPLETE"),
    (lambda e:e.update(selection_tag="latest"),"FINALIZED_SELECTION_REQUIRED"),
    (lambda e:e.update(chain_id=1),"CHAIN_MISMATCH"),
    (lambda e:e["cursor"].update(verified_hash="0x"+"c"*64),"CURSOR_REORG"),
])
def test_anchored_contract_fails_closed(mutation,reason):
    e=evidence();mutation(e);r=evaluate(e)
    assert not r["anchored_valid"] and r["reason"]==reason
    assert not r["ready_for_arm"] and not r["submit_allowed"]


def test_exact_500_ms_boundary_and_future_rejection():
    e=evidence();e["inventory_observed_ms"]=500;assert evaluate(e)["anchored_valid"]
    e["inventory_observed_ms"]=1001;assert not evaluate(e)["anchored_valid"]
