"""Authorized two-candidate DIAGNOSTIC. No execution guard bypass or HTTP POST."""
import asyncio,copy,json,math,os,re,sys,time
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient
from analysis.d6.real_execution_calibration_v1.core import digest
from analysis.d6.real_execution_calibration_v1.observation_collector import ReadBudget,bounded_pages
from analysis.d6.real_execution_calibration_v1.observed_trades import address,identifier,amount
from analysis.d6.real_execution_calibration_v1.log_schema import public_asset

EOA='0x9348efd557a09e644795c8f114bcf0bef86f203a'
D6='0x871d37b430c42ddbd0bbd37c29c02a2974109de9'
CLOB='https://clob.polymarket.com';DATA='https://data-api.polymarket.com';GAMMA='https://gamma-api.polymarket.com';EXPLORER='https://polygon.blockscout.com'
ALLOWED={CLOB:{'/time','/balance-allowance','/data/orders','/data/trades'},DATA:{'/v2/status','/v2/positions','/v2/trades'},GAMMA:{'/markets'},EXPLORER:{'/api/v2/addresses/'+a+'/token-balances' for a in (EOA,D6)}}

class DiagnosticGET(GetOnlyTransport):
    def __init__(self,base,routes,*,budget,**kw):
        if base not in ALLOWED or not set(routes)<=ALLOWED[base] or (kw.get('headers') and (base!=CLOB or '/time' in routes)):raise ValueError('COMPARISON_GET_SCOPE')
        self.budget=budget;self.observations=[]
        super().__init__(base,routes,**kw);self.pinned=(self.base,self.routes,self.headers)
    async def get_json(self,path,params=None,headers=None):
        if headers is not None or (self.base,self.routes,self.headers)!=self.pinned or path not in self.routes or path not in ALLOWED[self.base]:raise ValueError('COMPARISON_GET_SCOPE')
        async with self.budget.lock:
            await self.budget.before();stamp=time.time_ns()//1000000
            try:
                raw=await super().get_json(path,params=params)
                query={k:v for k,v in (params or {}).items() if k in ('user','market','signature_type','asset_type','start','end','after','before','limit','taker_only','include_archived','filter_type','filter_amount')}
                self.observations.append(dict(endpoint=self.base+path,method='GET',query=query,cursor_supplied=bool((params or {}).get('cursor') or (params or {}).get('next_cursor')),started_ms=stamp,received_ms=time.time_ns()//1000000,response_digest=digest(raw)))
                return raw
            finally:
                if self.audit and self.audit[-1].get('http_status')==429:self.budget.limited=True

def confirm_candidates(root):
    from app.live.l2_existing_reader import EXPECTED
    from app.live.genesis_ledger import read_genesis,expected_wallet
    from polymarket._internal.wallet import classify_account,signature_type_for
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    from analysis.d6.real_execution_calibration_v1.selection import inspect_selection
    from analysis.d6.real_execution_calibration_v1.v1_binding import verify
    old=json.loads((root/'analysis/d6/real_execution_calibration_v1/evidence/PHASE6_ASSESSMENT.json').read_text())
    prior=read_genesis(root/'runtime/d6_genesis.db')
    if old['observation_account'].lower()!=EOA or old['canonical_d6_account'].lower()!=D6 or EXPECTED.lower()!=EOA or prior['snapshot']['wallet'].lower()!=D6 or expected_wallet().lower()!=D6:raise ValueError('PUBLIC_CANDIDATE_BINDING_CONFLICT')
    selected=inspect_selection(root)
    if any(b!='CONFIG_EOA_AND_CANONICAL_D6_WALLET_CONFLICT_REQUIRES_OWNER_CHOICE' for b in selected['blockers']):raise ValueError('OTHER_STARTUP_GUARD_BLOCKED')
    contexts=[]
    for wallet in (EOA,D6):
        identity=classify_account(signer=EOA,wallet=wallet,config=env.wallet_derivation)
        st=signature_type_for(identity.wallet_type)
        if st!=(0 if wallet==EOA else 3):raise ValueError('SDK_CANDIDATE_CLASSIFICATION')
        contexts.append(dict(account=wallet,signer=EOA,wallet_type=identity.wallet_type,balance_get_signature_type=st,semantics='Explicit SDK-supported per-request wallet type; not a config mutation or echoed account proof'))
    return dict(contexts=contexts,strategy_hashes=verify(),artifact_identity_confirmed=True,genesis_identity_confirmed=True,source_genesis_digest=prior['snapshot_sha256'],startup_execution_conflict_preserved=not selected['selection_ready'])

def status_metadata(value,depth=0):
    if depth>5:return None
    if type(value) is dict:
        return {k:status_metadata(v,depth+1) for k,v in list(value.items())[:32] if re.fullmatch('[A-Za-z0-9_]{1,64}',k) and not re.search('secret|password|signature|api.?key|auth',k,re.I)}
    if type(value) is list:return [status_metadata(v,depth+1) for v in value[:10]]
    if type(value) in (bool,int) or value is None:return value
    if type(value) is float:return value if math.isfinite(value) else None
    if type(value) is str and re.fullmatch('[A-Za-z0-9_ .:+/-]{1,128}',value):return value
    return None

def safe_reason(exc):
    s=str(exc)
    return s if re.fullmatch('[A-Z0-9_]{1,100}',s) else type(exc).__name__

def numeric(v):
    if type(v) not in (str,int,float) or type(v) is float and not math.isfinite(v):raise ValueError('DATA_NUMERIC_SCHEMA')
    d=Decimal(str(v))
    if not d.is_finite() or d<0:raise ValueError('DATA_NUMERIC_SCHEMA')
    return d

async def data_rows(transport,path,wallet,start,end):
    params=dict(user=wallet,limit=50)
    if path=='/v2/trades':params.update(start=start,end=end,taker_only=False)
    else:params.update(include_archived=True,filter_type='TOKENS',filter_amount=0)
    seen=set();cursor=None;total=0;nonzero=0;times=[];markets=set();complete=False
    for page in range(2):
        raw=await transport.get_json(path,params={**params,**({'cursor':cursor} if cursor else {})})
        if type(raw) is not dict or type(raw.get('data')) is not list or type(raw.get('pagination')) is not dict or len(raw['data'])>50:raise ValueError('DATA_PAGE_SCHEMA')
        for row in raw['data']:
            if type(row) is not dict or address(row.get('proxy_wallet'))!=wallet:raise ValueError('DATA_FOREIGN_ACCOUNT')
            token=row.get('token_id');condition=row.get('condition_id')
            if not public_asset(token) or type(condition) is not str or not re.fullmatch('0x[0-9a-fA-F]{64}',condition):raise ValueError('DATA_MARKET_ASSET_SCHEMA')
            if path=='/v2/trades':
                stamp=row.get('timestamp')
                if type(stamp) is not int or not start<=stamp<=end or row.get('side') not in ('BUY','SELL') or not 0<numeric(row['price'])<1 or numeric(row['size'])<=0:raise ValueError('DATA_TRADE_WINDOW_OR_SCHEMA')
                tx=row.get('transaction_hash')
                if type(tx) is not str or not re.fullmatch('0x[0-9a-fA-F]{64}',tx):raise ValueError('DATA_TRADE_TRANSACTION_SCHEMA')
                key=(tx,token,stamp,row['side'],str(row['size']),str(row['price']));times.append(stamp)
            else:
                key=token;size=numeric(row['current_size']);nonzero+=int(size>0)
            if key in seen:raise ValueError('DATA_DUPLICATE_OR_AMBIGUOUS_ROW')
            seen.add(key);markets.add(condition);total+=1
        pg=raw['pagination'];more=pg.get('has_more');nxt=pg.get('next_cursor')
        if type(more) is not bool or (more and (type(nxt) is not str or not nxt or nxt==cursor)) or (not more and nxt is not None):raise ValueError('DATA_CURSOR_SCHEMA')
        if not more:complete=True;break
        cursor=nxt
    return dict(status='OBSERVED_ADDRESS_SCOPED_INDEX',count=total,nonzero_positions=nonzero if path.endswith('positions') else None,pages=page+1,pagination_complete=complete,window_start=start if path.endswith('trades') else None,window_end=end if path.endswith('trades') else None,oldest_trade_seconds=min(times) if times else None,newest_trade_seconds=max(times) if times else None,markets_count=len(markets),scope='ALL_MARKETS_LAST_30_DAYS_MAX_100_ROWS' if path.endswith('trades') else 'CURRENT_INDEX_POSITIONS_INCLUDING_ARCHIVED_MAX_100_ROWS',global_complete=False,indexer_asof_proven=False)

async def credential_orders(transport):
    from polymarket._internal.actions import account as a
    result={EOA:0,D6:0};seen=set();cursor=None;complete=False
    for page in range(2):
        path,params=a.build_list_open_orders_request(cursor=cursor);raw=await transport.get_json(path,params=params)
        if type(raw) is not dict or type(raw.get('data')) is not list or len(raw['data'])>200:raise ValueError('ORDER_PAGE_SCHEMA')
        for r in raw['data']:
            oid=identifier(r['id']);wallet=address(r['maker_address'])
            if oid in seen or wallet not in result or not public_asset(r.get('asset_id',r.get('token_id'))) or type(r.get('market')) is not str or not re.fullmatch('0x[0-9a-fA-F]{64}',r['market']):raise ValueError('ORDER_ATTRIBUTION')
            if r.get('side') not in ('BUY','SELL') or not 0<amount(r['price'])<1 or amount(r['original_size'])<amount(r['size_matched']):raise ValueError('ORDER_VALUE_SCHEMA')
            seen.add(oid);result[wallet]+=1
        parsed=a.parse_open_orders_page(raw)
        if not parsed.has_more:complete=True;break
        if parsed.next_cursor==cursor:raise ValueError('ORDER_CURSOR')
        cursor=parsed.next_cursor
    return dict(status='OBSERVED_CREDENTIAL_VIEW',candidate_counts=result,pagination_complete=complete,pages=page+1,scope='ONE_SIGNER_CREDENTIAL_VIEW_ATTRIBUTED_BY_RETURNED_MAKER_ADDRESS',wallet_global_scope_proven=False)

async def explorer_balance(transport,wallet,contract):
    raw=await transport.get_json('/api/v2/addresses/'+wallet+'/token-balances')
    if type(raw) is not list or len(raw)>2000:raise ValueError('EXPLORER_SCHEMA')
    found=[]
    for entry in raw:
        token=entry.get('token',{}) if type(entry) is dict else {}
        if str(token.get('address_hash',token.get('address',''))).lower()==contract.lower():
            value=entry.get('value')
            if type(value) is not str or not re.fullmatch('[0-9]+',value) or str(token.get('decimals'))!='6' or token.get('symbol')!='pUSD':raise ValueError('EXPLORER_COLLATERAL_SCHEMA')
            found.append(value)
    if len(found)>1:raise ValueError('EXPLORER_DUPLICATE_TOKEN')
    return dict(status='OBSERVED_EXPLORER_INDEX',balance_raw=found[0] if found else None,collateral_contract=contract,requested_symbol='pUSD',documented_decimals=6,token_metadata_observed=bool(found),absence_is_not_zero=True,scope='EXPLICIT_ADDRESS_INDEXED_TOKEN_BALANCES',state_asof_proven=False,limitation='No token-balance block/timestamp in this route; HTTP receive time is not state freshness')

def decide(report):
    # Only observed evidence may choose. Current API limitations are NOT waived.
    reasons=[];positive=[]
    for wallet,row in report['candidates'].items():
        bal=row.get('balance_first',{});again=row.get('balance_second',{});chain=row.get('explorer_balance',{});pos=row.get('positions',{})
        if bal.get('balance_raw') is None or again.get('balance_raw')!=bal.get('balance_raw'):reasons.append(wallet+':CLOB_BALANCE_UNAVAILABLE_OR_CHANGED')
        if chain.get('balance_raw') is None or chain.get('balance_raw')!=bal.get('balance_raw'):reasons.append(wallet+':NO_CONVERGENT_ADDRESS_COLLATERAL_BALANCE')
        if chain.get('state_asof_proven') is not True:reasons.append(wallet+':ADDRESS_BALANCE_FRESHNESS_UNPROVEN')
        if pos.get('status')!='OBSERVED_ADDRESS_SCOPED_INDEX' or not pos.get('pagination_complete') or not pos.get('indexer_asof_proven'):reasons.append(wallet+':POSITION_INDEX_SCOPE_OR_FRESHNESS_UNPROVEN')
        if bal.get('balance_raw') is not None and int(bal['balance_raw'])>0 or (pos.get('nonzero_positions') or 0)>0:positive.append(wallet)
        for key in ('history','selected_market_clob_trades'):
            if row.get(key,{}).get('status','BLOCKED')=='BLOCKED':reasons.append(wallet+':'+key.upper()+'_UNQUALIFIED')
    if report.get('orders',{}).get('status')!='OBSERVED_CREDENTIAL_VIEW' or report['orders'].get('wallet_global_scope_proven') is not True:reasons.append('CLOB_ORDERS_CREDENTIAL_SCOPE_NOT_WALLET_GLOBAL')
    if len(positive)!=1:reasons.append('BOTH_CANDIDATES_ACTIVE_OR_NO_UNIQUE_CURRENT_ACTIVITY')
    return dict(status='CALIBRATION_BLOCKED' if reasons else 'RECONCILIATION_ACCOUNT_EVIDENCED',account=None if reasons else positive[0],signer=EOA,reasons=reasons,live_ready=False,submit_allowed=False)

async def compare(root):
    from app.live.l2_existing_reader import load_existing
    from polymarket._internal.hmac import build_hmac_signature
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    from polymarket._internal.actions import account as a
    from analysis.d6.real_execution_calibration_v1.observed_trades import collect_scoped_trades
    report=dict(mode='TWO_AUTHORIZED_CANDIDATES_GET_ONLY_DIAGNOSTIC',started_ms=time.time_ns()//1000000,candidates={},no_execution_guard_bypass=True,http_post_count=0,submit_allowed=False)
    creds=None;transports=[];audit=[];budget=ReadBudget(limit=30,interval=.35)
    try:
        report['identity']=confirm_candidates(root)
        creds,report['storage']=load_existing(root)
        if not creds:raise ValueError('EXISTING_PROTECTED_CREDENTIALS_UNAVAILABLE')
        async def headers(path):
            if path not in ('/balance-allowance','/data/orders','/data/trades'):raise ValueError('AUTH_GET_ROUTE')
            stamp=int(time.time())
            return {'POLY_ADDRESS':EOA,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],'POLY_TIMESTAMP':str(stamp),'POLY_SIGNATURE':build_hmac_signature(secret=creds['secret'],timestamp=stamp,method='GET',path=path,body=None)}
        def transport(base,routes,**kw):
            t=DiagnosticGET(base,routes,budget=budget,audit=audit,**kw);transports.append(t);return t
        public=transport(CLOB,('/time',));clob=transport(CLOB,('/balance-allowance','/data/orders','/data/trades'),headers=headers)
        data=transport(DATA,('/v2/status','/v2/positions','/v2/trades'));gamma=transport(GAMMA,('/markets',));explorer=transport(EXPLORER,ALLOWED[EXPLORER])
        async def stage(op):
            stamp=time.time_ns()//1000000
            try:result=await asyncio.wait_for(op(),30)
            except Exception as exc:result=dict(status='BLOCKED',reason=safe_reason(exc))
            return {**result,'started_ms':stamp,'finished_ms':time.time_ns()//1000000}
        server=await public.get_json('/time')
        if type(server) is not int or abs(server-time.time())>5:raise ValueError('TIME_PREFLIGHT')
        now=int(time.time());start=now-30*86400;slot=now//300*300
        async def status():
            raw=await data.get_json('/v2/status')
            return dict(status='OBSERVED_SERVICE_STATUS',public_status_metadata=status_metadata(raw),response_digest=digest(raw),schema_keys=sorted(k for k in raw if re.fullmatch('[A-Za-z0-9_]{1,64}',k)) if type(raw) is dict else [],per_account_ingestion_boundary_proven=False)
        report['data_service_status']=await stage(status)
        market=None
        try:
            from app.collectors.polymarket import PolymarketMarketDiscovery
            from app.d5.identity import MarketIdentity
            raw=await gamma.get_json('/markets',params={'slug':'btc-updown-5m-'+str(slot)})
            if type(raw) is not list or len(raw)!=1 or raw[0].get('active') is not True or raw[0].get('closed') is not False:raise ValueError('MARKET_SCHEMA')
            parsed=PolymarketMarketDiscovery.parse_market_list(raw)
            if len(parsed)!=1:raise ValueError('MARKET_AMBIGUOUS')
            market=MarketIdentity.from_market(parsed[0])
            if market.market_slug!='btc-updown-5m-'+str(slot) or market.expiry_ts_ms!=(slot+300)*1000:raise ValueError('MARKET_WINDOW')
            report['selected_market']=market.fields()
        except Exception:report['selected_market']={'status':'BLOCKED'}
        async def balance(st):
            path,params=a.build_balance_allowance_request(asset_type='COLLATERAL',signature_type=st)
            raw=await clob.get_json(path,params=params);value=raw.get('balance') if type(raw) is dict else None
            if type(value) is not str or not re.fullmatch('[0-9]+',value):raise ValueError('BALANCE_SCHEMA')
            return dict(status='OBSERVED_TYPE_CONTEXT_BALANCE',balance_raw=value,units='BASE_UNITS',collateral_contract=env.collateral_token,documented_symbol='pUSD',documented_decimals=6,signature_type_query=st,account_echoed=False,account_binding='SDK_TYPE_CONTEXT_REQUIRES_INDEPENDENT_ADDRESS_CORROBORATION',allowance_fields_ignored=True)
        report['orders']=await stage(lambda:credential_orders(clob))
        for context in report['identity']['contexts']:
            wallet=context['account'];st=context['balance_get_signature_type'];row={'context':context};report['candidates'][wallet]=row
            row['balance_first']=await stage(lambda:balance(st))
            row['positions']=await stage(lambda:data_rows(data,'/v2/positions',wallet,start,now))
            row['history']=await stage(lambda:data_rows(data,'/v2/trades',wallet,start,now))
            if market:
                client=ReadOnlyClient(wallet=wallet,signature_type=st,clob=clob,data=data)
                async def selected_trades():
                    summary,_=await collect_scoped_trades(client,account=wallet,market=market.condition_id,tokens=(market.token_up,market.token_down),start_seconds=slot,expiry_ms=market.expiry_ts_ms,clock=lambda:time.time_ns()//1000000)
                    summary['request_scope']='SHARED_SIGNER_CREDENTIAL_VIEW_WITH_MARKET_WINDOW_NOT_ADDRESS_FILTERED';return summary
                row['selected_market_clob_trades']=await stage(selected_trades)
            else:row['selected_market_clob_trades']={'status':'BLOCKED','reason':'NO_VERIFIED_MARKET'}
            row['explorer_balance']=await stage(lambda:explorer_balance(explorer,wallet,env.collateral_token))
        for context in report['identity']['contexts']:
            report['candidates'][context['account']]['balance_second']=await stage(lambda:balance(context['balance_get_signature_type']))
        report['verdict']=decide(report)
    except Exception as exc:report['verdict']=dict(status='CALIBRATION_BLOCKED',account=None,signer=EOA,reasons=[safe_reason(exc)],submit_allowed=False)
    finally:
        report['finished_ms']=time.time_ns()//1000000;report['requests']=audit;report['provenance']=[o for t in transports for o in t.observations]
        report['limits']=dict(get_limit=30,get_count=len(audit),min_spacing_ms=350,pagination_pages=2,rows_per_data_page=50,retries=0,rate_limited=budget.limited)
        for t in transports:t.close()
        if creds:
            if any(v in json.dumps(report) for v in creds.values()):report={'verdict':{'status':'CALIBRATION_BLOCKED','reason':'SECRET_REPORT_GUARD'},'submit_allowed':False}
            creds.clear()
    return report

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--authorized-compare',action='store_true');args=p.parse_args()
    if not args.authorized_compare:raise SystemExit('Explicit two-candidate GET-only comparison authorization required')
    result=asyncio.run(compare(ROOT))
    folder=Path(__file__).parent/'evidence'/('candidate_comparison_'+str(time.time_ns()//1000000));folder.mkdir(parents=True,exist_ok=False)
    path=folder/'comparison.json'
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({'artifact':str(path),'verdict':result['verdict']['status'],'http_get_count':result.get('limits',{}).get('get_count'),'http_post_count':0,'submit_allowed':False}))

if __name__=='__main__':main()
