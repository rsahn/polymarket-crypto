import asyncio,copy,types
import pytest
from .compare_accounts import DiagnosticGET,ReadBudget,EOA,D6,CLOB,DATA,EXPLORER,ALLOWED,data_rows,decide,confirm_candidates,status_metadata

@pytest.mark.parametrize('base,path',[(CLOB,'/order'),(CLOB,'/cancel'),(CLOB,'/auth/derive-api-key'),(CLOB,'/balance-allowance/update'),('https://polygon.drpc.org','/'),(EXPLORER,'/api')])
def test_diagnostic_does_not_allow_post_or_unreviewed_routes(base,path):
    with pytest.raises(ValueError):DiagnosticGET(base,[path],budget=ReadBudget())

def test_candidate_id_confirmation_is_public_only(tmp_path,monkeypatch):
    import json
    p=tmp_path/'analysis/d6/real_execution_calibration_v1/evidence';p.mkdir(parents=True)
    (p/'PHASE6_ASSESSMENT.json').write_text(json.dumps({'observation_account':EOA,'canonical_d6_account':D6}))
    monkeypatch.setattr('app.live.genesis_ledger.read_genesis',lambda p:{'snapshot':{'wallet':D6},'snapshot_sha256':'a'*64})
    monkeypatch.setattr('analysis.d6.real_execution_calibration_v1.selection.inspect_selection',lambda p:{'blockers':['CONFIG_EOA_AND_CANONICAL_D6_WALLET_CONFLICT_REQUIRES_OWNER_CHOICE'],'selection_ready':False})
    monkeypatch.setattr('analysis.d6.real_execution_calibration_v1.v1_binding.verify',lambda:{'fixture.py':'b'*64})
    result=confirm_candidates(tmp_path)
    assert [r['account'] for r in result['contexts']]==[EOA,D6]
    assert [r['balance_get_signature_type'] for r in result['contexts']]==[0,3]
    assert result['artifact_identity_confirmed'] and result['startup_execution_conflict_preserved']

class Data:
    def __init__(self,row):self.row=row;self.requests=[]
    async def get_json(self,path,params):
        self.requests.append((path,params))
        return {'data':[self.row],'pagination':{'has_more':False,'next_cursor':None}}

def fixture_row():return {'proxy_wallet':D6,'condition_id':'0x'+'a'*64,'token_id':'123','current_size':2,'timestamp':150,'transaction_hash':'0x'+'b'*64,'side':'BUY','price':0.5,'size':2}

def test_address_history_and_positions_are_validated_before_counting():
    for path in ['/v2/trades','/v2/positions']:
        t=Data(fixture_row());r=asyncio.run(data_rows(t,path,D6,100,200))
        assert r['count']==1 and not r['global_complete'] and not r['indexer_asof_proven']
        assert t.requests[0][1]['user']==D6
        bad=fixture_row();bad['proxy_wallet']=EOA
        with pytest.raises(ValueError):asyncio.run(data_rows(Data(bad),path,D6,100,200))

@pytest.mark.parametrize('change',[{'timestamp':True},{'timestamp':201},{'timestamp':99},{'price':float('nan')},{'size':False},{'token_id':'bad'},{'condition_id':'foreign'}])
def test_malformed_history_never_becomes_counted(change):
    raw={**fixture_row(),**change}
    with pytest.raises(ValueError):asyncio.run(data_rows(Data(raw),'/v2/trades',D6,100,200))

def base_report():
    report={'candidates':{},'orders':{'status':'OBSERVED_CREDENTIAL_VIEW','wallet_global_scope_proven':True}}
    for wallet,bal in [(EOA,'0'),(D6,'100000000')]:
        report['candidates'][wallet]={'balance_first':{'balance_raw':bal},'balance_second':{'balance_raw':bal},'explorer_balance':{'balance_raw':bal,'state_asof_proven':True},'positions':{'status':'OBSERVED_ADDRESS_SCOPED_INDEX','pagination_complete':True,'indexer_asof_proven':True,'nonzero_positions':0},'history':{'status':'OBSERVED_ADDRESS_SCOPED_INDEX'},'selected_market_clob_trades':{'status':'OBSERVED_ATTRIBUTED'}}
    return report

def test_choice_requires_convergent_current_evidence_not_derivation_or_old_trade():
    report=base_report();assert decide(report)['account']==D6
    for mutation in ['freshness','contradiction','scope','both_active','both_empty']:
        r=copy.deepcopy(report)
        if mutation=='freshness':r['candidates'][D6]['explorer_balance']['state_asof_proven']=False
        if mutation=='contradiction':r['candidates'][D6]['explorer_balance']['balance_raw']='0'
        if mutation=='scope':r['orders']['wallet_global_scope_proven']=False
        if mutation=='both_active':r['candidates'][EOA]['positions']['nonzero_positions']=1
        if mutation=='both_empty':
            for k in ['balance_first','balance_second','explorer_balance']:r['candidates'][D6][k]['balance_raw']='0'
        assert decide(r)['status']=='CALIBRATION_BLOCKED' and decide(r)['account'] is None

def test_public_status_projection_excludes_sensitive_fields():
    assert status_metadata({'api_key':'CANARY','last_updated':'2026-09-27T12:00:00Z'})=={'last_updated':'2026-09-27T12:00:00Z'}

def test_get_transport_rejects_mutated_origin_before_authentication():
    t=DiagnosticGET(CLOB,['/time'],budget=ReadBudget());t.base='https://other.invalid'
    with pytest.raises(ValueError):asyncio.run(t.get_json('/time'))

def test_missing_explorer_token_is_unknown_not_zero_or_verified_metadata():
    from .compare_accounts import explorer_balance
    class Empty:
        async def get_json(self,path):return []
    r=asyncio.run(explorer_balance(Empty(),D6,'0x'+'c'*40))
    assert r['balance_raw'] is None and r['absence_is_not_zero']
    assert r['token_metadata_observed'] is False and r['state_asof_proven'] is False
