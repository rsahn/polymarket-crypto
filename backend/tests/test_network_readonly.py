import asyncio
import pytest


def test_only_explicit_get_routes():
    from app.live.network_readonly import GetOnlyTransport
    t=GetOnlyTransport("https://clob.polymarket.com",{"/time"})
    with pytest.raises(ValueError):asyncio.run(t.get_json("/order"))
    with pytest.raises(ValueError):asyncio.run(t.get_json("https://evil.test/time"))
    assert not hasattr(t,"post_json") and not hasattr(t,"delete_json")


def test_no_redirect_following():
    from app.live.network_readonly import NoRedirect
    assert NoRedirect().redirect_request(None,None,302,"",{},"https://evil.test") is None


def test_snapshot_never_claims_stream_sync():
    from app.live.network_readonly import qualify_book
    row={"asset_id":"u","market":"c","timestamp":"1000","bids":[{"price":".5","size":"2"}],"asks":[{"price":".6","size":"3"}]}
    r=qualify_book([row,dict(row,asset_id="d")],tokens=["u","d"],condition="c",slug="m",now=1000)
    assert r["schema_valid"] and not r["available"] and not r["book_synced"]


def test_wrong_asset_rejected():
    from app.live.network_readonly import qualify_book
    assert not qualify_book([],tokens=["u","d"],condition="c",slug="m",now=1000)["available"]


def test_facade_has_no_mutating_methods():
    from app.live.network_readonly import ReadOnlyClient
    assert not any(hasattr(ReadOnlyClient,n) for n in ("create","place_limit_order","cancel_order","deploy","sign_order"))


def test_error_audit_never_logs_secret_or_query(monkeypatch):
    import urllib.error
    from app.live.network_readonly import GetOnlyTransport
    class Opener:
        def open(self,request,timeout):
            assert request.get_method()=="GET"
            raise urllib.error.HTTPError("https://clob.polymarket.com/time?secret=SECRET",403,"SECRET",{},None)
    monkeypatch.setattr("urllib.request.build_opener",lambda *a:Opener())
    t=GetOnlyTransport("https://clob.polymarket.com",{"/time"})
    with pytest.raises(RuntimeError,match="READ_FAILED"):
        asyncio.run(t.get_json("/time",params={"secret":"SECRET"},headers={"POLY_API_KEY":"SECRET"}))
    assert "SECRET" not in str(t.audit) and t.audit[0]["http_status"]==403


@pytest.mark.parametrize("base",["http://clob.polymarket.com","https://user:secret@clob.polymarket.com","https://clob.polymarket.com?secret=x"])
def test_invalid_base_rejected(base):
    from app.live.network_readonly import GetOnlyTransport
    with pytest.raises(ValueError):GetOnlyTransport(base,{"/time"})


def test_user_agent_differential_403_vs_working_request(monkeypatch):
    import urllib.request,urllib.error
    from app.live.network_readonly import GetOnlyTransport
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b"1790000000"
    class Edge:
        def open(self,request,timeout):
            # Reproduce the reported differential, not a live server diagnosis.
            if request.get_header("User-agent")!="Mozilla/5.0":
                raise urllib.error.HTTPError(request.full_url,403,"Forbidden",{},None)
            assert request.full_url=="https://clob.polymarket.com/time"
            assert request.get_method()=="GET" and request.data is None
            return Response()
    monkeypatch.setattr(urllib.request,"build_opener",lambda *a:Edge())
    control=urllib.request.Request("https://clob.polymarket.com/time",headers={"User-Agent":"Mozilla/5.0"})
    assert Edge().open(control,8).status==200
    assert asyncio.run(GetOnlyTransport("https://clob.polymarket.com",{"/time"}).get_json("/time"))==1790000000
