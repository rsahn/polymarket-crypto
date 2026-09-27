"""Explicit bound one-shot GET observation adapter; not an execution authority."""
import asyncio,copy,json,os,re,time
from decimal import Decimal
from pathlib import Path
from .compare_accounts import ROOT,EOA,D6,CLOB,DATA,GAMMA,DiagnosticGET,ReadBudget,confirm_candidates,safe_reason,numeric,status_metadata
from .binding_consumer import consume,envelope,require
from .observed_trades import address,identifier,amount,collect_scoped_trades
from .log_schema import public_asset
from .core import digest
from .adapters import AccountAdapter
from .observation_timing import TimedTransport,timed_stage,now_ms
from app.live.network_readonly import ReadOnlyClient

GAPS={
 'wallet_completeness':'Queried credential orders/market-window trades/indexed positions do not certify the full wallet universe.',
 'atomic_frontier':'These GET contracts provide no shared account snapshot ID, mutation sequence or verifiable lineage across cash/orders/trades/positions.',
 'native_fee_effects':'No independently final attributed cash/share fee effects are available from this observation batch; a rate or CONFIRMED label is not a settlement effect.',
 'round_trip_fee_bound':'No qualified round-trip conservative fee bound is supplied by these responses.',
 'execution_runtime':'This reader does not sign, instantiate a monetary client or qualify an order-capable runtime.',
 'operator_custody':'No real recovery drill or specific-exposure human acceptance is established by account reads.',
 'fine_clock':'Integer-second server time is a coarse preflight only, not the required fine clock bound.'}

def validate_balance(raw,binding):
    require(type(raw) is dict,'BALANCE_RAW_SCHEMA')
    for key in ('wallet','maker_address','account','funder'):
        if key in raw:require(address(raw[key])==D6,'BALANCE_ACCOUNT_CONTRADICTION')
    if 'signer' in raw:require(address(raw['signer'])==EOA,'BALANCE_SIGNER_CONTRADICTION')
    if 'collateral_contract' in raw:require(address(raw['collateral_contract'])==binding['collateral_contract'].lower(),'BALANCE_COLLATERAL_CONTRADICTION')
    if 'asset_type' in raw:require(raw['asset_type']=='COLLATERAL','BALANCE_ASSET_TYPE_CONTRADICTION')
    if 'signature_type' in raw:require(type(raw['signature_type']) is int and raw['signature_type']==3,'BALANCE_SIGNATURE_CONTEXT_CONTRADICTION')
    v=raw.get('balance');require(type(v) is str and re.fullmatch('[0-9]+',v) is not None,'BALANCE_RAW_SCHEMA')
    return dict(status='AVAILABLE_SCOPED',balance_raw=v,balance_pusd=str(Decimal(v)/10**6),collateral_contract=binding['collateral_contract'],decimals=6,scope='AUTHENTICATED_TYPE3_BALANCE_WITH_VALIDATED_D6_IDENTITY',cash_state_block=None,allowance_fields_ignored=True,binding_basis='VALIDATED_IDENTITY_PLUS_GET_CONTEXT_NOT_FRESH_CHAIN_RECHECK')

async def read_orders(clob):
    from polymarket._internal.actions import account as a
    accepted=[];seen=set();cursors=set();cursor=None;complete=False
    for page in range(2):
        path,params=a.build_list_open_orders_request(cursor=cursor);raw=await clob.get_json(path,params=params)
        require(type(raw) is dict and type(raw.get('data')) is list and len(raw['data'])<=100,'ORDER_PAGE_SCHEMA_OR_CAP')
        now=int(time.time())
        for r in raw['data']:
            require(type(r) is dict,'ORDER_ROW_SCHEMA');oid=identifier(r['id'])
            require(address(r['maker_address'])==D6,'ORDER_FOREIGN_ACCOUNT')
            require(oid not in seen,'ORDER_DUPLICATE');seen.add(oid)
            token_id=r.get('asset_id',r.get('token_id'));condition=r.get('market')
            require(public_asset(token_id) and ('asset_id' not in r or 'token_id' not in r or r['asset_id']==r['token_id']),'ORDER_ASSET_SCHEMA')
            require(type(condition) is str and re.fullmatch('0x[0-9a-fA-F]{64}',condition) is not None,'ORDER_MARKET_SCHEMA')
            require(type(r.get('side')) is str and r['side'] in ('BUY','SELL'),'ORDER_SIDE_SCHEMA')
            require(type(r.get('status')) is str and r['status'] in ('LIVE','DELAYED','UNMATCHED'),'ORDER_OPEN_STATUS_AMBIGUOUS')
            require(type(r.get('created_at')) is int and 0<r['created_at']<=now,'ORDER_TIMESTAMP_SCHEMA')
            price=amount(r['price']);size=amount(r['original_size']);matched=amount(r['size_matched'])
            require(0<price<1 and size>0 and 0<=matched<size,'ORDER_QUANTITY_SCHEMA')
            accepted.append(dict(order_id=oid,account=D6,market=condition,token=token_id,side=r['side'],status=r['status'],price=str(price),original_shares=str(size),matched_shares=str(matched)))
        parsed=a.parse_open_orders_page(raw)  # only after strict raw validation
        if not parsed.has_more:complete=True;break
        nxt=parsed.next_cursor
        require(type(nxt) is str and nxt and nxt not in cursors,'ORDER_CURSOR');cursors.add(nxt);cursor=nxt
    return dict(status='AVAILABLE_SCOPED',rows=accepted,count=len(accepted),pages=page+1,pagination_complete=complete,scope='ALL_MARKETS_AVAILABLE_SIGNER_CREDENTIAL_VIEW_ATTRIBUTED_D6',wallet_complete=None)

async def read_positions(data):
    rows=[];seen=set();cursors=set();cursor=None;complete=False
    params=dict(user=D6,limit=50,include_archived=True,filter_type='TOKENS',filter_amount=0)
    for page in range(2):
        raw=await data.get_json('/v2/positions',params={**params,**({'cursor':cursor} if cursor else {})})
        require(type(raw) is dict and type(raw.get('data')) is list and len(raw['data'])<=50 and type(raw.get('pagination')) is dict,'POSITION_PAGE_SCHEMA_OR_CAP')
        for r in raw['data']:
            require(type(r) is dict and address(r.get('proxy_wallet'))==D6,'POSITION_FOREIGN_ACCOUNT')
            token_id=r.get('token_id');condition=r.get('condition_id')
            require(public_asset(token_id) and token_id not in seen,'POSITION_ASSET_DUPLICATE_OR_SCHEMA');seen.add(token_id)
            require(type(condition) is str and re.fullmatch('0x[0-9a-fA-F]{64}',condition) is not None,'POSITION_MARKET_SCHEMA')
            require(type(r.get('status')) is str and r['status'] in ('OPEN','REDEEMABLE','REDEEMABLE_LOST','MERGEABLE','CLOSED'),'POSITION_STATUS_SCHEMA')
            require(type(r.get('current_size')) in (int,float),'POSITION_NUMBER_WIRE_SCHEMA')
            size=numeric(r['current_size']);require(r['status']!='CLOSED' or size==0,'POSITION_CLOSED_WITH_BALANCE');rows.append(dict(token=token_id,account=D6,market=condition,shares=str(size),status=r['status']))
        pg=raw['pagination'];more=pg.get('has_more');nxt=pg.get('next_cursor')
        require(type(more) is bool and ((more and type(nxt) is str and bool(nxt) and nxt not in cursors) or (not more and nxt is None)),'POSITION_CURSOR')
        if not more:complete=True;break
        cursors.add(nxt);cursor=nxt
    return dict(status='AVAILABLE_SCOPED_INDEX',rows=rows,count=len(rows),pages=page+1,pagination_complete=complete,scope='D6_CURRENT_INDEX_ALL_MARKETS_INCLUDING_ARCHIVED',wallet_complete=None,account_state_asof=None)

class CachedReader:
    def __init__(self,value,clock):self.value=copy.deepcopy(value);self.clock=clock
    async def read(self):
        r=copy.deepcopy(self.value)
        if r.get('available') and not 0<=self.clock()-r['observed_ms']<=5000:r.update(available=False,reason='OBSERVATION_EXPIRED_REACQUIRE_EXPLICITLY')
        return r

def wire_projection(checks,clock=lambda:time.time_ns()//1000000):
    b=checks.get('balance',{});o=checks.get('orders',{});t=checks.get('trades',{});p=checks.get('positions',{})
    timed=lambda x:x.get('timing_schema')=='READ_INTERVALS_OLDEST_ANCHOR/1' and type(x.get('freshness_anchor_ms')) is int
    a_ok=all(timed(x) for x in (b,o,t)) and b.get('status')=='AVAILABLE_SCOPED' and o.get('status')=='AVAILABLE_SCOPED' and t.get('status')=='OBSERVED_ATTRIBUTED'
    p_ok=timed(p) and p.get('status')=='AVAILABLE_SCOPED_INDEX'
    a=dict(available=a_ok,wallet=D6,collateral_symbol='pUSD',scope={'orders':o.get('scope'),'trades':t.get('scope'),'wallet_complete':None,'atomic_frontier':None})
    pos=dict(available=p_ok,wallet=D6,collateral_symbol='pUSD',scope=p.get('scope'))
    if a_ok:a.update(observed_ms=min(x.get('freshness_anchor_ms',x['observed_ms']) for x in (b,o,t)),balance_collateral=b['balance_pusd'],open_order_ids=[r['order_id'] for r in o['rows']],trade_ids=[r['trade_id'] for r in t['rows']])
    if p_ok:pos.update(observed_ms=p.get('freshness_anchor_ms',p['observed_ms']),balances={r['token']:r['shares'] for r in p['rows']})
    return AccountAdapter(CachedReader(a,clock),CachedReader(pos,clock),account=D6,collateral='pUSD',clock=clock)

class BoundObservationAdapter:
    def __init__(self,binding,client,public,gamma,selectors=None,clock=now_ms):
        require(binding.get('identity_only') is True and binding.get('account')==D6 and binding.get('signer')==EOA and type(binding.get('signature_type')) is int and binding['signature_type']==3,'ADAPTER_BINDING')
        require(client.wallet==D6 and client.signature_type==3,'ADAPTER_CLIENT_CONTEXT')
        self.clock=clock
        client.clob=TimedTransport(client.clob,clock);client.data=TimedTransport(client.data,clock)
        public=TimedTransport(public,clock);gamma=TimedTransport(gamma,clock)
        self.transports=(client.clob,client.data,public,gamma)
        self.binding=copy.deepcopy(binding);self.client=client;self.public=public;self.gamma=gamma;self.used=False
        self.selectors=copy.deepcopy(selectors or {});self._selector_digest=digest(self.selectors)
        self._digest=digest(binding);self._context=(client,client.wallet,client.signature_type,client.clob,client.data,public,gamma)
    def check_context(self):
        require(digest(self.binding)==self._digest and digest(self.selectors)==self._selector_digest and self._context==(self.client,self.client.wallet,self.client.signature_type,self.client.clob,self.client.data,self.public,self.gamma),'ADAPTER_CONTEXT_CHANGED')
    async def observe(self):
        self.check_context()
        require(not self.used,'ONE_SHOT_ADAPTER_ALREADY_USED');self.used=True
        r=dict(mode='BOUND_D6_ONE_SHOT_DIAGNOSTIC',binding=self.binding,started_ms=self.clock(),checks={},capabilities={},cash_from_historical_binding_used=False,submit_allowed=False,calibration_ready=False)
        checks=r['checks'];market=None;start=self.clock()//300000*300;expiry=(start+300)*1000
        async def stage(name,op):
            if self.clock()>=expiry:
                checks[name]=dict(status='UNAVAILABLE',reason='MARKET_EXPIRED_BEFORE_READ',rows=None,count=None);return
            checks[name]=await timed_stage(op,self.transports,clock=self.clock,expiry_ms=expiry)
        async def clock():
            before=self.clock();s=await self.public.get_json('/time');after=self.clock()
            require(type(s) is int and abs(s*1000-after)<=5000,'CLOCK_PREFLIGHT')
            return dict(status='AVAILABLE_COARSE_ONLY',offset_ms=s*1000-(before+after)//2,uncertainty_ms=1000+(after-before)//2)
        await stage('clock',clock)
        async def market_read():
            nonlocal market
            from app.collectors.polymarket import PolymarketMarketDiscovery
            from app.d5.identity import MarketIdentity
            slug='btc-updown-5m-'+str(start)
            explicit={v['value'] for k in ('MARKET_SLUG','POLYMARKET_MARKET_SLUG') for v in self.selectors.get(k,[])}
            require(not explicit or explicit=={slug},'CONFIG_MARKET_DIAGNOSTIC_CONFLICT')
            raw=await self.gamma.get_json('/markets',params={'slug':slug})
            require(type(raw) is list and len(raw)==1 and raw[0].get('active') is True and raw[0].get('closed') is False,'MARKET_SELECTION')
            parsed=PolymarketMarketDiscovery.parse_market_list(raw);require(len(parsed)==1,'MARKET_AMBIGUOUS')
            market=MarketIdentity.from_market(parsed[0]);require(market.market_slug=='btc-updown-5m-'+str(start) and market.expiry_ts_ms==(start+300)*1000,'MARKET_WINDOW')
            for key,actual in (('CONDITION_ID',market.condition_id),('TOKEN_UP',market.token_up),('TOKEN_DOWN',market.token_down)):
                require(all(v['value']==actual for v in self.selectors.get(key,[])),'CONFIG_MARKET_IDENTITY_CONFLICT')
            return dict(status='AVAILABLE_SCOPED',**market.fields(),scope='CURRENT_V1_SLOT')
        await stage('market',market_read)
        async def balance():
            from polymarket._internal.actions import account as a
            path,params=a.build_balance_allowance_request(asset_type='COLLATERAL',signature_type=3)
            return validate_balance(await self.client.clob.get_json(path,params=params),self.binding)
        if checks['clock']['status']=='AVAILABLE_COARSE_ONLY':
            await stage('balance',balance)
            await stage('orders',lambda:read_orders(self.client.clob))
            if market and checks['market']['status']=='AVAILABLE_SCOPED':
                async def trades():
                    summary,rows=await collect_scoped_trades(self.client,account=D6,market=market.condition_id,tokens=(market.token_up,market.token_down),start_seconds=start,expiry_ms=market.expiry_ts_ms,clock=self.clock)
                    summary['rows']=rows if summary['status']=='OBSERVED_ATTRIBUTED' else None
                    summary['request_scope']='SIGNER_CREDENTIAL_VIEW_MARKET_AND_TIME_FILTERED_RAW_D6_ATTRIBUTION_REQUIRED';return summary
                await stage('trades',trades)
            else:checks['trades']={'status':'UNAVAILABLE','reason':'MARKET_UNQUALIFIED'}
        else:
            for k in ('balance','orders','trades'):checks[k]={'status':'UNAVAILABLE','reason':'CLOCK_PREFLIGHT'}
        await stage('positions',lambda:read_positions(self.client.data))
        async def status():
            raw=await self.client.data.get_json('/v2/status')
            require(type(raw) is dict and type(raw.get('data')) is dict,'DATA_SERVICE_SCHEMA')
            return dict(status='AVAILABLE_SERVICE_TELEMETRY',metadata=status_metadata(raw),per_account_frontier=None)
        await stage('data_service',status)
        self.check_context()
        try:
            require(self.clock()<expiry,'MARKET_EXPIRED_BEFORE_PROJECTION')
            r['account_adapter_projection']=dict(status='AVAILABLE_DIAGNOSTIC_NOT_EXECUTION',snapshot=await wire_projection(checks,clock=self.clock).snapshot())
        except Exception as exc:r['account_adapter_projection']=dict(status='UNAVAILABLE',reason=safe_reason(exc))
        r['capabilities']={k:dict(status='UNAVAILABLE_FOR_EXECUTION',reason=v) for k,v in GAPS.items()}
        r['finished_ms']=self.clock()
        for v in checks.values():
            if 'valid_until_ms' in v:v['fresh_at_collection_end']=v.get('status')!='UNAVAILABLE' and v['valid_until_ms']>=r['finished_ms'] and r['finished_ms']<expiry
        return r

async def run_bound(binding):
    from app.live.l2_existing_reader import load_existing
    from polymarket._internal.hmac import build_hmac_signature
    identity=confirm_candidates(ROOT)  # all existing startup safety checks; diagnostic exception only for known account conflict
    from .selection import inspect_selection
    startup=inspect_selection(ROOT);creds=None;ts=[];audit=[];budget=ReadBudget(limit=10,interval=.35)
    try:
        creds,storage=load_existing(ROOT)
        require(bool(creds) and storage.get('storage_validated') is True,'EXISTING_CREDENTIALS_UNAVAILABLE')
        async def headers(path):
            require(path in ('/balance-allowance','/data/orders','/data/trades'),'HMAC_GET_ROUTE')
            stamp=int(time.time())
            return {'POLY_ADDRESS':EOA,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],'POLY_TIMESTAMP':str(stamp),'POLY_SIGNATURE':build_hmac_signature(secret=creds.get('secret'),timestamp=stamp,method='GET',path=path,body=None)}
        def transport(base,routes,**kw):
            t=DiagnosticGET(base,routes,budget=budget,audit=audit,**kw);ts.append(t);return t
        clob=transport(CLOB,('/balance-allowance','/data/orders','/data/trades'),headers=headers);data=transport(DATA,('/v2/positions','/v2/status'))
        public=transport(CLOB,('/time',));gamma=transport(GAMMA,('/markets',))
        client=ReadOnlyClient(wallet=D6,signature_type=3,clob=clob,data=data)
        report=await BoundObservationAdapter(binding,client,public,gamma,selectors=startup['selectors']).observe()
        report.update(storage=storage,startup_selection_unchanged=startup,actual_signature_selectors=startup['selectors'].get('READONLY_SIGNATURE_TYPE',[]),actual_signature_selector_conflict=any(v['value']!='3' for v in startup['selectors'].get('READONLY_SIGNATURE_TYPE',[])),legacy_eoa_type0_incompatible=True,global_config_changed=False)
    except Exception as exc:report=dict(mode='BOUND_D6_ONE_SHOT_DIAGNOSTIC',status='BLOCKED',reason=safe_reason(exc),submit_allowed=False)
    finally:
        report.update(requests=audit,provenance=[o for t in ts for o in t.observations],request_budget=10,pages_per_view_max=2,retries=0,rate_limited=budget.limited,rpc_requests=0)
        for t in ts:t.close()
        if creds:
            if any(v in json.dumps(report) for v in creds.values()):report={'status':'BLOCKED_SECRET_REPORT_GUARD','submit_allowed':False}
            creds.clear()
    return report

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--authorized-bound-diagnostic',action='store_true');p.add_argument('--legacy-binding',required=True);args=p.parse_args()
    require(args.authorized_bound_diagnostic,'EXPLICIT_DIAGNOSTIC_REQUIRED')
    legacy=Path(args.legacy_binding);v=envelope(legacy)
    folder=Path(__file__).parent/'evidence'/('bound_observation_'+str(time.time_ns()//1000000));folder.mkdir(parents=True,exist_ok=False)
    def save(name,obj):
        with (folder/name).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    save('binding_v1.json',v);binding=consume(folder/'binding_v1.json',legacy)
    result=asyncio.run(run_bound(binding));save('qualification_matrix.json',result)
    print(json.dumps({'artifact':str(folder/'qualification_matrix.json'),'get_count':len(result.get('requests',[])),'rpc_requests':0,'submit_allowed':False,'projection':result.get('account_adapter_projection',{}).get('status'),'checks':{k:v['status'] for k,v in result.get('checks',{}).items()}}))
if __name__=='__main__':main()
