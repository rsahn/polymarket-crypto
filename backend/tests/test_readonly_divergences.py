import asyncio
import urllib.parse
import httpx
from app.live.network_readonly import GetOnlyTransport
from polymarket._internal.actions.data import list_positions_spec


def test_positions_wire_query_matches_installed_sdk(monkeypatch):
    import urllib.request
    captured=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return b'{}'
    class Opener:
        def open(self,request,timeout):captured.append(request.full_url);return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    spec=list_positions_spec(user='0x'+'1'*40,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0)
    params={**spec.base_params,'limit':100}
    asyncio.run(GetOnlyTransport('https://data-api.polymarket.com',('/v2/positions',)).get_json(spec.path,params=params))
    sent=urllib.parse.parse_qs(urllib.parse.urlsplit(captured[0]).query)
    expected=urllib.parse.parse_qs(str(httpx.QueryParams(params)))
    assert sent==expected
    assert sent['include_archived']==['true']

def test_balance_identity_diagnostic_not_silent_wallet_switch():
    from app.live.readonly_diagnostics import request_diagnostics
    from app.live.l2_existing_reader import EXPECTED
    import json
    r=request_diagnostics(EXPECTED,EXPECTED)
    assert r['balance_current']['query']=={'asset_type':'COLLATERAL','signature_type':0}
    assert r['balance_historical_code']['query']=={'asset_type':'COLLATERAL','signature_type':3}
    assert not r['balance_current']['token_id_sent'] and not r['balance_current']['spender_query_sent']
    assert not r['collateral_proof']['conversion_allowed']
    assert EXPECTED not in json.dumps(r)
    assert not r['deposit_candidates_public_computation_only']['deployment_or_balance_verified']

def test_real_execution_store_schema_is_read_for_reconciliation(tmp_path):
    import sqlite3,json
    from test_stored_l2_qualification import run
    p=tmp_path/'real_schema_fixture.db'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE execution_state (id INTEGER PRIMARY KEY,value TEXT)')
        db.execute('INSERT INTO execution_state VALUES(1,?)',(json.dumps({'phase':'RECOVERY_REQUIRED','bought':5.0,'sold':2.0,'entry_id':'hidden','exit_id':'hidden'}),))
    result,_=run(local=str(p))
    state=result['qualification']['reconciliation']
    assert state['local_state_read'] is True
    assert state['local_has_open_shares'] is True and state['complete'] is False
