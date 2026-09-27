"""Explicit identity import. Historical cash is NEVER a current observation."""
import json,time
from pathlib import Path
from importlib.metadata import version
from .compare_accounts import EOA,D6
from .identify_account import CONTRACT,assess
from .core import digest
from .v1_binding import verify

SCHEMA='D6_RECONCILIATION_IDENTITY/1'
LEGACY='ACCOUNT_IDENTITY_20260927_V0'
SCOPE='EXPLICIT_RECONCILIATION_IDENTITY_ONLY_REACQUIRE_CASH_FOR_LIVE_USE'

def require(ok,reason):
    if not ok:raise ValueError(reason)

def read_json(path):
    with Path(path).open('rb') as f:data=f.read(1000001)
    require(len(data)<=1000000,'BINDING_SIZE');return json.loads(data)

def legacy_identity(path):
    path=Path(path);b=read_json(path)
    require(type(b) is dict and b.get('source_evidence')=='evidence.json','BINDING_SOURCE_PATH')
    require(not any(k in b for k in ('schema','schema_version','version')),'UNSUPPORTED_LEGACY_VERSION')
    e=read_json(path.parent/'evidence.json')
    require(b.get('source_digest')==digest(e),'BINDING_SOURCE_DIGEST')
    require(e.get('mode')=='AUTHORIZED_PINNED_CASH_ACCOUNT_IDENTIFICATION','BINDING_LEGACY_PROFILE')
    require(b.get('status')=='ACCOUNT_IDENTIFIED' and b.get('scope')==SCOPE,'BINDING_SCOPE')
    require(b.get('reconciliation_account')==D6 and b.get('signer')==EOA and type(b.get('signature_type')) is int and b['signature_type']==3,'BINDING_ROLES')
    require(type(b.get('chain_id')) is int and b['chain_id']==137 and b.get('collateral_contract')==CONTRACT,'BINDING_CHAIN_CONTRACT')
    for k in ('calibration_ready','submit_allowed','automatic_startup_override'):require(b.get(k) is False,'BINDING_NO_OVERRIDE')
    require(e['identity'].get('strategy_hashes')==verify(),'BINDING_STRATEGY_VERSION')
    require(assess(e).get('reconciliation_account')==D6 and e['verdict'].get('reconciliation_account')==D6,'BINDING_EVIDENCE_SEMANTICS')
    require(e.get('submit_allowed') is False and e['verdict'].get('calibration_ready') is False and e['verdict'].get('submit_allowed') is False,'BINDING_SOURCE_NO_EXECUTION')
    require(type(e.get('finished_ms')) is int and 0<e['finished_ms']<=time.time_ns()//1000000,'BINDING_FUTURE_OR_INVALID_TIME')
    require(type(b.get('cash_observation_valid_until_ms')) is int and b['cash_observation_valid_until_ms']==e['finished_ms']+5000,'BINDING_HISTORICAL_CASH_WINDOW')
    require(b.get('block')==e['chain'].get('block') and b.get('observed_ms')==e.get('finished_ms'),'BINDING_TIME_BLOCK')
    require(e.get('explicit_context',{}).get('reconciliation_account')==D6 and e['explicit_context'].get('signer')==EOA and e['explicit_context'].get('signature_type')==3,'BINDING_SOURCE_CONTEXT')
    return b,e

def envelope(path):
    b,e=legacy_identity(path)
    return dict(schema=SCHEMA,schema_version=1,legacy_input_profile=LEGACY,legacy_binding_digest=digest(b),source_digest=digest(e),sdk_version='0.11.0',strategy_hashes=verify(),identity_binding=b,role_scope='IDENTITY_ONLY_NOT_CASH_OR_EXECUTION',automatic_override=False)

def consume(path,legacy_path):
    v=read_json(path)
    require(type(v) is dict and v.get('schema')==SCHEMA and type(v.get('schema_version')) is int and v['schema_version']==1,'BINDING_VERSION')
    require(v.get('legacy_input_profile')==LEGACY and v.get('role_scope')=='IDENTITY_ONLY_NOT_CASH_OR_EXECUTION' and v.get('automatic_override') is False,'BINDING_PROFILE_SCOPE')
    require(v.get('sdk_version')==version('polymarket-client')=='0.11.0','BINDING_SDK_VERSION')
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    require(env.collateral_token==CONTRACT and env.chain_id==137,'BINDING_CURRENT_SDK_CONTRACT')
    b,e=legacy_identity(legacy_path)
    require(v.get('legacy_binding_digest')==digest(b) and v.get('source_digest')==digest(e) and v.get('identity_binding')==b and v.get('strategy_hashes')==verify(),'BINDING_ENVELOPE_DIGEST')
    return dict(schema=SCHEMA,account=D6,signer=EOA,signature_type=3,collateral_contract=CONTRACT,collateral_symbol=e['chain']['symbol'],collateral_decimals=e['chain']['decimals'],historical_identity_observed_ms=b['observed_ms'],source_digest=b['source_digest'],current_cash=None,cash_reacquisition_required=True,identity_only=True,automatic_startup_override=False)
