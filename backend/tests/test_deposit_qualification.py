import asyncio
import json
import pytest
from app.live.deposit_qualification import qualify_deposit, positions_error, write_report
from app.live.l2_existing_reader import EXPECTED


def run_case(deployed=(True,False),balance='109160000',fail_balance=False):
    calls=[];loads=[]
    class Fake:
        def __init__(self,base,routes,**kw):self.base=base;self.kw=kw
        async def get_json(self,path,params=None,headers=None):
            calls.append((path,params))
            if path=='/time':return 1000
            if path=='/deployed':return {'deployed':deployed[sum(p=='/deployed' for p,_ in calls)-1]}
            if path=='/balance-allowance':
                assert params=={'asset_type':'COLLATERAL','signature_type':3}
                assert self.kw['headers']
                await self.kw['headers'](path)
                if fail_balance:raise RuntimeError('private failure detail')
                return {'balance':balance,'allowances':{}}
            if path=='/v2/positions':return {'data':[], 'pagination':{'has_more':False,'next_cursor':None}}
            raise AssertionError(path)
    def load():loads.append(1);return {'apiKey':'fake-api-key','secret':'c2VjcmV0','passphrase':'fake-passphrase'},{'storage_validated':True}
    result=asyncio.run(qualify_deposit(load,transport=Fake,clock=lambda:1000000))
    return result,calls,loads


def test_unique_legacy_proof_gates_type3_and_comparison():
    r,c,l=run_case()
    assert r['deposit_wallet_proven'] is True and r['deposit_kind']=='legacy'
    assert r['balance_type3_raw']=='109160000' and r['historical_comparison']=='EQUAL_RAW_UNITS_NOT_ATTESTED'
    assert r['positions_status']=='PASS_INDEX_ONLY' and len(l)==1
    assert [x[0] for x in c]==['/time','/deployed','/deployed','/balance-allowance','/v2/positions']
    assert r['conversion_allowed'] is False and r['complete'] is False
    out=json.dumps(r)
    assert all(x not in out for x in [EXPECTED,'fake-api-key','c2VjcmV0','fake-passphrase','private failure detail'])


@pytest.mark.parametrize('deployed',[(False,False),(True,True),('true',False),(None,True)])
def test_ambiguous_or_invalid_proof_never_loads_l2(deployed):
    r,c,l=run_case(deployed)
    assert not r['deposit_wallet_proven'] and not l
    assert not any(p=='/balance-allowance' for p,_ in c)


def test_beacon_only():
    r,_,_=run_case((False,True),balance='0')
    assert r['deposit_kind']=='beacon' and r['historical_comparison']=='DIFFERENT_RAW_IDENTITY_TIME_NOT_ATTESTED'


def test_auth_failure_no_fallback_positions_independent():
    r,c,_=run_case(fail_balance=True)
    assert r['balance_type3_raw'] is None
    assert sum(p=='/balance-allowance' for p,_ in c)==1
    assert r['positions_status']=='PASS_INDEX_ONLY'


def test_error_diagnostic_never_echoes_untrusted_body():
    raw=b'{"error":"invalid include_archived fake-secret 0x123456"}'
    result=positions_error(raw)
    assert result['parameters_mentioned']==['include_archived']
    assert 'fake-secret' not in json.dumps(result) and '0x123456' not in json.dumps(result)
    assert result['exact_cause_proven'] is False


def test_report_no_overwrite(tmp_path):
    p=tmp_path/'report.json';write_report(p,{'complete':False})
    with pytest.raises(FileExistsError):write_report(p,{'complete':True})
    assert json.loads(p.read_text())=={'complete':False}


def test_transport_allowlist_and_no_write_surface():
    from app.live.deposit_qualification import ProbeTransport,CLOB,DATA,RELAYER
    for base,route in [(CLOB,'/auth/derive-api-key'),(CLOB,'/balance-allowance/update'),(RELAYER,'/submit'),(DATA,'/positions')]:
        with pytest.raises(ValueError):ProbeTransport(base,(route,))
    p=ProbeTransport(CLOB,('/time',))
    assert not hasattr(p,'post') and not hasattr(p,'delete')
    with pytest.raises(ValueError):asyncio.run(p.get_json('/order'))
    with pytest.raises(ValueError):ProbeTransport(DATA,('/v2/positions',),headers=lambda:None)


def test_positions_http400_structured_diagnostic_and_lowercase_wire(monkeypatch):
    import io
    import urllib.error
    import urllib.request
    from app.live.deposit_qualification import ProbeTransport,DATA
    seen=[];audit=[]
    class Opener:
        def open(self,request,timeout):
            seen.append(request)
            payload=b'{"detail":[{"loc":["query","include_archived"],"type":"bool_parsing","input":"fake-private-value"}]}'
            raise urllib.error.HTTPError(request.full_url,400,'never echo',{},io.BytesIO(payload))
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    with pytest.raises(RuntimeError,match='POSITIONS_HTTP_FAILED'):
        asyncio.run(ProbeTransport(DATA,('/v2/positions',),audit=audit).get_json('/v2/positions',params={'include_archived':True}))
    assert 'include_archived=true' in seen[0].full_url and seen[0].method=='GET'
    assert audit[0]['validation']['exact_cause_proven'] is True
    assert audit[0]['validation']['validation_issues']==[{'parameter':'include_archived','code':'bool_parsing'}]
    assert 'fake-private-value' not in json.dumps(audit)


def test_redirect_handler_refuses_even_same_host():
    from app.live.network_readonly import NoRedirect
    assert NoRedirect().redirect_request(None,None,302,'',{},'https://clob.polymarket.com/time') is None


def test_stale_time_never_checks_deployment_or_loads_credentials():
    from app.live.deposit_qualification import CLOB
    calls=[]
    class Fake:
        def __init__(self,*a,**kw):pass
        async def get_json(self,path,**kw):calls.append(path);return 0
    def load():raise AssertionError('must not load')
    r=asyncio.run(qualify_deposit(load,transport=Fake,clock=lambda:1000000))
    assert calls==['/time'] and not r['deposit_wallet_proven']
