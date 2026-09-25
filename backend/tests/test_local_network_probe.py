import asyncio
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]

def module():
    spec=importlib.util.spec_from_file_location("local_probe",ROOT/"analysis/qualify_local_readonly.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Fake:
    calls=[]
    def __init__(self,base,routes,**kw):self.base=base;self.routes=routes
    async def get_json(self,path,params=None,**kw):
        assert path in self.routes
        self.calls.append((self.base,path))
        if path=="/time":return 1000
        if path=="/api/geoblock":return {"blocked":False,"ip":"SECRET_IP","country":"PT","region":"11"}
        if path=="/markets":return []
        if path=="/v2/positions":return {"data":[],"next_cursor":None}
        raise RuntimeError("SECRET_ERROR")


def test_public_reads_continue_without_credentials():
    m=module();Fake.calls=[]
    r=asyncio.run(m.qualify({},transport=Fake,clock=lambda:1000000))
    assert r["qualification"]["account"]["status"]=="BLOCKED"
    assert r["qualification"]["time"]["status"]=="PASS"
    assert r["qualification"]["geo"]["blocked"] is False
    assert r["complete"] is False and r["ready_for_arm"] is False
    assert len(r["checks"])==12
    assert "SECRET_IP" not in json.dumps(r) and "SECRET_ERROR" not in json.dumps(r)
    assert not any("auth" in path for _,path in Fake.calls)


def test_enabled_flag_blocks_before_network():
    m=module();Fake.calls=[]
    r=asyncio.run(m.qualify({"REAL_ORDERS_ENABLED":"true"},transport=Fake))
    assert not Fake.calls and r["checks"]["live_flags_disabled"] is False


def test_config_does_not_load_private_keys(tmp_path):
    m=module();p=tmp_path/".env"
    p.write_text("PRIVATE_KEY=SECRET\nREAL_ORDERS_ENABLED=false\n")
    assert "PRIVATE_KEY" not in m.read_config(p,{})


def test_output_is_exclusive_and_redacts_config(tmp_path):
    m=module();p=tmp_path/"READINESS_LOCAL_NETWORK.json"
    m.write_report(p,{"status":"BLOCKED"})
    with pytest.raises(FileExistsError):m.write_report(p,{})


def test_wrong_sdk_version_never_contacts_network(monkeypatch):
    m=module();Fake.calls=[];monkeypatch.setattr(m,"version",lambda _:"999")
    r=asyncio.run(m.qualify({},transport=Fake))
    assert not Fake.calls and r["status"]=="BLOCKED_SDK_VERSION"


def test_authenticated_gets_and_report_redaction(monkeypatch):
    m=module()
    from polymarket import AsyncSecureClient
    def forbidden(*a,**kw):raise AssertionError("SDK_CONSTRUCTOR_FORBIDDEN")
    monkeypatch.setattr(AsyncSecureClient,"create",forbidden)
    class AuthFake(Fake):
        def __init__(self,base,routes,**kw):
            super().__init__(base,routes,**kw);self.headers=kw.get("headers")
        async def get_json(self,path,params=None,**kw):
            if self.headers:
                headers=await self.headers(path)
                assert headers["POLY_API_KEY"]=="redact-key-123"
            if path=="/balance-allowance":
                return {"balance":"1000000","allowances":{"0xE111180000d2663C0091e4f400237545B87B996B":"25000000"}}
            if path in ("/data/orders","/data/trades"):return {"data":[],"next_cursor":"LTE="}
            if path=="/markets":return [{"slug":"btc-updown-5m-900","conditionId":"c","clobTokenIds":["1","2"]}]
            if path=="/book":return {"asset_id":params["token_id"],"market":"c","timestamp":"1000000","bids":[{"price":".5","size":"10"}],"asks":[{"price":".6","size":"10"}]}
            return await super().get_json(path,params,**kw)
    config={"READONLY_CLOB_API_KEY":"redact-key-123","READONLY_CLOB_API_SECRET":"cmVkYWN0LXNlY3JldA==","READONLY_CLOB_API_PASSPHRASE":"redact-pass-123",
        "READONLY_SIGNER_ADDRESS":"0x"+"1"*40,"POLYMARKET_WALLET_ADDRESS":"0x"+"1"*40,"READONLY_SIGNATURE_TYPE":"0"}
    r=asyncio.run(m.qualify(config,transport=AuthFake,clock=lambda:1000000))
    text=json.dumps(r)
    assert all(v not in text for k,v in config.items() if k!="READONLY_SIGNATURE_TYPE")
    assert r["qualification"]["account"]["status"]=="PASS_READ_ONLY"
    assert r["qualification"]["account"]["balance_collateral"]=="1"
    assert r["qualification"]["orders"]["pagination_complete"] is True
    assert r["qualification"]["book"]["schema_valid"] is True
    assert r["checks"]["book_freshness"] is False and r["checks"]["balance_usdc"] is False
    assert r["complete"] is False


def test_all_network_errors_still_produce_twelve_checks():
    m=module()
    class Offline(Fake):
        async def get_json(self,*a,**k):raise RuntimeError("private credential must never appear")
    r=asyncio.run(m.qualify({},transport=Offline))
    assert len(r["checks"])==12 and not r["ready_for_arm"]
    assert "private credential" not in json.dumps(r)


def test_flag_conflict_cannot_be_overridden(tmp_path):
    m=module();p=tmp_path/".env";p.write_text("REAL_ORDERS_ENABLED=true\n")
    config=m.read_config(p,{"REAL_ORDERS_ENABLED":"false"})
    assert config["REAL_ORDERS_ENABLED"]!="false"


def test_public_only_calls_three_routes_without_config():
    m=module();Fake.calls=[]
    r=asyncio.run(m.qualify_public(transport=Fake,clock=lambda:1000000,environ={}))
    assert [p for _,p in Fake.calls]==["/time","/api/geoblock","/markets"]
    assert r["mode"]=="public-only" and r["credentials_loaded"] is False
    assert len(r["checks"])==12


def test_public_only_cli_never_reads_dotenv(monkeypatch,tmp_path):
    m=module();output=tmp_path/"new.json"
    def forbidden(*a,**k):raise AssertionError("CONFIG_MUST_NOT_LOAD")
    monkeypatch.setattr(m,"read_config",forbidden)
    async def public():return {"mode":"public-only","credentials_loaded":False}
    monkeypatch.setattr(m,"qualify_public",public)
    monkeypatch.setattr("sys.argv",["probe","--public-only","--output",str(output)])
    assert m.main()==0 and json.loads(output.read_text())["credentials_loaded"] is False


def test_public_default_output_preserves_old_report(monkeypatch,tmp_path):
    m=module();monkeypatch.setattr(m,"ROOT",tmp_path)
    old=tmp_path/"READINESS_LOCAL_NETWORK.json";old.write_text("original")
    async def public():return {"mode":"public-only"}
    monkeypatch.setattr(m,"qualify_public",public)
    monkeypatch.setattr("sys.argv",["probe","--public-only"])
    assert m.main()==0 and old.read_text()=="original"
    assert len(list(tmp_path.glob("READINESS_LOCAL_NETWORK_PUBLIC_*.json")))==1


def test_public_flags_reject_before_get():
    m=module();Fake.calls=[]
    r=asyncio.run(m.qualify_public(transport=Fake,environ={"LIVE_EXECUTION_ARMED":"true"}))
    assert not Fake.calls and not r["checks"]["live_flags_disabled"]
