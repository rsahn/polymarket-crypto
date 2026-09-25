"""Independent GET-only qualification stages; no private-key or recovery imports."""
import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from decimal import Decimal
from .network_readonly import GetOnlyTransport, ReadOnlyClient
from .production_readonly import drain, plain, number

CLOB='https://clob.polymarket.com'
DATA='https://data-api.polymarket.com'
FLAGS=('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')


def blocked(reason):return {'status':'BLOCKED','complete':False,'reason':reason}


def local_snapshot(path):
    if not path:return None
    p=Path(path).resolve(strict=True)
    with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=2) as db:
        db.execute('PRAGMA query_only=ON')
        row=db.execute('SELECT value FROM execution_state WHERE id=1').fetchone()
    if not row:raise ValueError()
    state=json.loads(row[0])
    if not isinstance(state,dict):raise ValueError()
    return state


async def qualify(config,*,transport=GetOnlyTransport,client_factory=ReadOnlyClient,clock=None):
    clock=clock or (lambda:time.time_ns()//1_000_000)
    q={};audit=[];rows={}
    report={'qualification':q,'requests':audit,'complete':False,'ready_for_arm':False,'submit_allowed':False,
            'provenance':{'live_flags_disabled':{'source':'process','status':'PASS'}},'authenticated_get_attempts':0}
    if any(config.get(k,'false')!='false' for k in FLAGS):
        report['status']='BLOCKED_LIVE_FLAGS';return report
    from importlib.metadata import version
    if version('polymarket-client')!='0.11.0':report['status']='BLOCKED_SDK_VERSION';return report
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    from polymarket._internal.hmac import build_hmac_signature
    signer=config['READONLY_SIGNER_ADDRESS'];wallet=config['POLYMARKET_WALLET_ADDRESS']
    from .readonly_diagnostics import request_diagnostics
    report['request_diagnostics']=request_diagnostics(signer,wallet)
    routes=('/balance-allowance','/data/orders','/data/trades')
    public=transport(CLOB,('/time',),audit=audit)
    async def headers(path):
        if path not in routes:raise ValueError()
        stamp=clock()//1000
        return {'POLY_ADDRESS':signer,'POLY_API_KEY':config['READONLY_CLOB_API_KEY'],
                'POLY_PASSPHRASE':config['READONLY_CLOB_API_PASSPHRASE'],'POLY_TIMESTAMP':str(stamp),
                'POLY_SIGNATURE':build_hmac_signature(secret=config['READONLY_CLOB_API_SECRET'],timestamp=stamp,method='GET',path=path,body=None)}
    client=client_factory(wallet=wallet,signature_type=int(config['READONLY_SIGNATURE_TYPE']),
        clob=transport(CLOB,routes,headers=headers,audit=audit),data=transport(DATA,('/v2/positions',),audit=audit))
    async def stage(name,operation):
        started=clock()
        try:result=await asyncio.wait_for(operation(),30)
        except Exception:result=blocked('GET_OR_CONTRACT_FAILED')
        result.update(started_ms=started,finished_ms=clock())
        q[name]=result
    async def preflight():
        stamp=await public.get_json('/time')
        if type(stamp) is not int or abs(clock()-stamp*1000)>5000:raise ValueError()
        return {'status':'PASS','server_seconds':stamp,'complete':False}
    await stage('time',preflight)
    q['collateral']={'status':'CONFIG_ONLY','asset_type':'COLLATERAL','contract':env.collateral_token,
                     'chain_id':env.chain_id,'provenance':'SDK 0.11.0 PRODUCTION_CONFIG',
                     'symbol_verified':False,'decimals_verified':False,'account_binding_verified':False}
    async def balance():
        value=plain(await client.get_balance_allowance(asset_type='COLLATERAL'))
        raw=number(value['balance'])
        if raw<0 or raw!=raw.to_integral_value() or not isinstance(value['allowances'],dict):raise ValueError()
        allowances=[number(v) for k,v in value['allowances'].items() if k.lower()==env.standard_exchange.lower()]
        if len(allowances)!=1 or allowances[0]<0 or allowances[0]!=allowances[0].to_integral_value():raise ValueError()
        return {'status':'PASS_READ_ONLY','balance_raw':str(raw),'allowance_raw':str(allowances[0]),
                'units':'base_units','conversion':'BLOCKED_DECIMALS_NOT_VERIFIED','complete':False}
    async def paginated(name):
        source=client.list_open_orders if name=='orders' else client.list_account_trades
        values=await drain(source());ids=set()
        for row in values:
            key=row.get('id')
            if not isinstance(key,str) or not key or key in ids:raise ValueError()
            ids.add(key)
            if name=='orders' and str(row.get('maker_address','')).lower()!=wallet.lower():raise ValueError()
        rows[name]=values
        return {'status':'PASS_READ_ONLY','count':len(values),'pagination_complete':True,'complete':False,
                'scope':'credential_view_not_global_wallet'}
    for name,op in [('balance_allowance',balance),('orders',lambda:paginated('orders')),('trades',lambda:paginated('trades'))]:
        if q['time']['status']=='PASS':await stage(name,op)
        else:q[name]=blocked('PUBLIC_TIME_PREFLIGHT_FAILED')
    async def positions():
        values=await drain(client.list_positions(user=wallet,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0))
        seen=set();nonzero=0
        for row in values:
            if str(row.get('wallet','')).lower()!=wallet.lower():raise ValueError()
            token=str(row['asset_id']);quantity=number(row['current_size'])
            if not token.isdigit() or token in seen or quantity<0:raise ValueError()
            seen.add(token);nonzero+=int(quantity>0)
        rows['positions']=values
        return {'status':'PASS_INDEX_ONLY','count':len(values),'nonzero_positions':nonzero,'pagination_complete':True,
                'complete':False,'conditional_balance_comparison':'BLOCKED_ASSET_TYPES_NOT_DEMONSTRATED'}
    await stage('positions',positions)
    q['reconciliation']=blocked('LOCAL_STATE_NOT_CONFIGURED')
    try:
        state=local_snapshot(config.get('READONLY_EXECUTION_STATE_DB'))
        if state is not None:
            phase=state.get('phase');bought=number(state['bought']);sold=number(state['sold'])
            opened=bought-sold
            if bought<0 or sold<0 or opened<0:raise ValueError()
            if phase not in {'CLOSED','RECOVERY_REQUIRED','ENTRY_SUBMIT_PENDING','ENTRY_ACKED','ENTRY_CANCEL_PENDING','EXIT_SUBMIT_PENDING','EXIT_ACKED','EXIT_CANCEL_PENDING'}:raise ValueError()
            if phase=='CLOSED' and opened!=0:raise ValueError()
            q['reconciliation']={'status':'BLOCKED','complete':False,'local_state_read':True,
                'local_closed':phase=='CLOSED','local_has_open_shares':opened>0,
                'remote_views_available':all(k in rows for k in ('orders','trades','positions')),
                'reason':'GLOBAL_COVERAGE_CONDITIONAL_BALANCES_AND_ATOMICITY_UNPROVEN'}
    except Exception:q['reconciliation']=blocked('LOCAL_STATE_READ_OR_SCHEMA_FAILED')
    report['authenticated_get_attempts']=sum(x.get('endpoint') in {CLOB+r for r in routes} for x in audit)
    report['status']='AUTHENTICATED_READ_ONLY_NOT_READY'
    return report
