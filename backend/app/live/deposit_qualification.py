"""Isolated GET qualification; only public wallet calculations and existing L2 HMAC."""
import asyncio
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from importlib.metadata import version
from .network_readonly import GetOnlyTransport, NoRedirect
from .l2_existing_reader import EXPECTED
from .production_readonly import number

CLOB='https://clob.polymarket.com'
DATA='https://data-api.polymarket.com'
RELAYER='https://relayer-v2.polymarket.com'
FLAGS=('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')
FIELDS={'user','filter_type','filter_amount','include_archived','limit','cursor','status'}
CODES={'missing','bool_parsing','int_parsing','float_parsing','enum','literal_error','greater_than_equal','less_than_equal','string_pattern_mismatch'}


def positions_error(raw):
    # Never echo server text, input values, URLs, account IDs or response headers.
    text=raw.decode('utf-8',errors='replace')
    result={'body_sha256':hashlib.sha256(raw).hexdigest(),
            'parameters_mentioned':sorted(k for k in FIELDS if re.search(r'\b'+k+r'\b',text)),
            'validation_issues':[], 'exact_cause_proven':False}
    try:
        obj=json.loads(text)
        details=obj.get('detail',[]) if isinstance(obj,dict) else []
        if isinstance(details,list):
            for item in details[:20]:
                if not isinstance(item,dict):continue
                loc=item.get('loc');code=item.get('type')
                if isinstance(loc,list) and len(loc)==2 and loc[0]=='query' and loc[1] in FIELDS and code in CODES:
                    result['validation_issues'].append({'parameter':loc[1],'code':code})
        result['exact_cause_proven']=bool(result['validation_issues'])
    except (ValueError,TypeError):pass
    return result


class ProbeTransport(GetOnlyTransport):
    def __init__(self,base,routes,**kw):
        allowed={CLOB:{'/time','/balance-allowance'},DATA:{'/v2/positions'},RELAYER:{'/deployed'}}
        if base not in allowed or not set(routes)<=allowed[base]:raise ValueError('ROUTE_REJECTED')
        if kw.get('headers') and (base!=CLOB or set(routes)!={'/balance-allowance'}):raise ValueError('AUTH_ROUTE_REJECTED')
        super().__init__(base,routes,**kw)
    async def get_json(self,path,params=None,headers=None):
        if headers is not None:raise ValueError('CUSTOM_HEADERS_REJECTED')
        if path not in self.routes:raise ValueError('ROUTE_REJECTED')
        if self.base!=DATA:return await super().get_json(path,params=params)
        params=params or {}
        if set(params)-FIELDS:raise ValueError('QUERY_REJECTED')
        def read():
            entry={'method':'GET','endpoint':DATA+path,'started_ms':time.time_ns()//1000000}
            try:
                query=urllib.parse.urlencode({k:str(v).lower() if type(v) is bool else v for k,v in params.items()})
                request=urllib.request.Request(DATA+path+'?'+query,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'},method='GET')
                with urllib.request.build_opener(NoRedirect()).open(request,timeout=8) as response:
                    entry['http_status']=response.status
                    raw=response.read(4000001)
                    if len(raw)>4000000:raise ValueError()
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                entry['http_status']=exc.code
                if exc.code==400:entry['validation']=positions_error(exc.read(65536))
                raise RuntimeError('POSITIONS_HTTP_FAILED') from None
            except Exception:
                raise RuntimeError('POSITIONS_READ_FAILED') from None
            finally:
                entry['finished_ms']=time.time_ns()//1000000
                self.audit.append(entry)
        return await asyncio.to_thread(read)


def write_report(path,report):
    with path.open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2)


async def qualify_deposit(load,*,transport=ProbeTransport,clock=None):
    clock=clock or (lambda:time.time_ns()//1000000)
    audit=[]
    report={'phase':'DEPOSIT_WALLET_READ_ONLY','deposit_wallet_proven':False,'deposit_kind':None,
            'balance_type3_raw':None,'historical_raw':'109160000','historical_comparison':'NOT_MEASURED',
            'positions_status':'BLOCKED_IDENTITY','conversion_allowed':False,'complete':False,
            'ready_for_arm':False,'submit_allowed':False,'private_key_loaded':False,'l1_signature_produced':False,
            'derive_attempted':False,'onchain_verified':False,'historical_instance_proven':False,
            'collateral_contract_verified':False,'decimals_verified':False,'account_binding_verified':False,
            'requests':audit,'blockers':[]}
    creds=None
    try:
        if version('polymarket-client')!='0.11.0':raise ValueError()
        from polymarket._internal.environment import PRODUCTION_CONFIG as env
        from polymarket._internal.wallet import derive_uups_deposit_wallet_address,derive_beacon_deposit_wallet_address
        if env.chain_id!=137 or env.relayer_url!=RELAYER:raise ValueError()
        candidates={'legacy':derive_uups_deposit_wallet_address(EXPECTED,env.wallet_derivation),
                    'beacon':derive_beacon_deposit_wallet_address(EXPECTED,env.wallet_derivation)}
        stamp=await transport(CLOB,('/time',),audit=audit).get_json('/time')
        if type(stamp) is not int or abs(clock()-stamp*1000)>5000:raise ValueError()
        relayer=transport(RELAYER,('/deployed',),audit=audit)
        deployed={}
        for kind,address in candidates.items():
            value=await relayer.get_json('/deployed',params={'address':address,'type':'WALLET'})
            if type(value) is not dict or type(value.get('deployed')) is not bool:raise ValueError()
            deployed[kind]=value['deployed']
        report['deployment_observations']=deployed
        selected=[k for k,v in deployed.items() if v]
        if len(selected)!=1:
            report['blockers'].append('NO_UNIQUE_DEPLOYED_CANDIDATE');return report
        kind=selected[0];wallet=candidates[kind]
        report.update(deposit_wallet_proven=True,deposit_kind=kind,wallet_masked=wallet[:6]+'...'+wallet[-4:],
                      proof_scope='SDK_CREATE2_SIGNER_ASSOCIATION_AND_PUBLIC_RELAYER_DEPLOYED_AT_OBSERVATION',
                      proof_limit='NOT_DIRECT_CHAIN_OWNER_PROOF_OR_HISTORICAL_SNAPSHOT')
        # Only now may existing, DPAPI-validated L2 be loaded. No other client or credential path.
        try:
            creds,storage=load();report['storage']=storage
            if not creds or storage.get('storage_validated') is not True:raise ValueError()
            from polymarket._internal.hmac import build_hmac_signature
            async def headers(path):
                if path!='/balance-allowance':raise ValueError()
                stamp=clock()//1000
                return {'POLY_ADDRESS':EXPECTED,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],
                        'POLY_TIMESTAMP':str(stamp),'POLY_SIGNATURE':build_hmac_signature(secret=creds['secret'],timestamp=stamp,method='GET',path=path,body=None)}
            value=await transport(CLOB,('/balance-allowance',),headers=headers,audit=audit).get_json('/balance-allowance',params={'asset_type':'COLLATERAL','signature_type':3})
            raw=number(value['balance'])
            if raw<0 or raw!=raw.to_integral_value() or not isinstance(value['allowances'],dict):raise ValueError()
            allowance=value['allowances'].get(env.standard_exchange)
            if allowance is not None:
                allowance=number(allowance)
                if allowance<0 or allowance!=allowance.to_integral_value():raise ValueError()
            report['allowance_selected_raw']=None if allowance is None else str(allowance)
            report['balance_type3_raw']=str(raw)
            report['historical_comparison']='EQUAL_RAW_UNITS_NOT_ATTESTED' if raw==109160000 else 'DIFFERENT_RAW_IDENTITY_TIME_NOT_ATTESTED'
        except Exception:report['blockers'].append('BALANCE_OR_STORAGE_FAILED_NO_RETRY')
        try:
            from .network_readonly import ReadOnlyClient
            from .production_readonly import drain
            client=ReadOnlyClient(wallet=wallet,signature_type=3,clob=None,data=transport(DATA,('/v2/positions',),audit=audit))
            rows=await drain(client.list_positions(user=wallet,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0))
            for row in rows:
                if str(row.get('wallet','')).lower()!=wallet.lower() or number(row['current_size'])<0:raise ValueError()
            report.update(positions_status='PASS_INDEX_ONLY',positions_count=len(rows),positions_pagination_complete=True)
        except Exception:
            report['positions_status']='BLOCKED_HTTP_OR_SCHEMA'
            report['blockers'].append('POSITIONS_FAILED_SEE_SANITIZED_REQUEST_DIAGNOSTIC')
        report['blockers'].extend(['COLLATERAL_CONTRACT_DECIMALS_AND_ACCOUNT_BINDING_UNPROVEN','GLOBAL_INVENTORY_AND_LOCAL_RECONCILIATION_UNPROVEN'])
    except Exception:report['blockers'].append('PREFLIGHT_OR_DEPLOYMENT_PROOF_FAILED')
    if creds and any(v in json.dumps(report) for v in creds.values()):
        return {'phase':'DEPOSIT_WALLET_READ_ONLY','complete':False,'deposit_wallet_proven':False,'status':'REDACTION_BLOCKED'}
    return report
