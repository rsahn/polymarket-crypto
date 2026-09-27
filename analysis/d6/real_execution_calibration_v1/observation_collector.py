"""Bounded explicit observations. No ledger input, signer, credential bootstrap or order API."""
import asyncio,copy,json,time,re
from dataclasses import dataclass
from .core import digest,dec
from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient,NoRedirect
from app.live.production_readonly import plain

ROUTES={'https://clob.polymarket.com':frozenset(('/time','/fee-rate','/balance-allowance','/data/orders','/data/trades')),'https://data-api.polymarket.com':frozenset(('/v2/positions',)),'https://gamma-api.polymarket.com':frozenset(('/markets',))}
class ReadBudget:
    def __init__(self,limit=12,interval=.25):self.limit=limit;self.count=0;self.interval=interval;self.next_start=0.;self.limited=False;self.lock=asyncio.Lock()
    async def before(self):
        if self.limited or self.count>=self.limit:raise ValueError('READ_BUDGET_OR_RATE_LIMIT')
        await asyncio.sleep(max(0,self.next_start-time.monotonic()))
        self.count+=1;self.next_start=time.monotonic()+self.interval

class ObservationGET(GetOnlyTransport):
    def __init__(self,base,routes,*,budget,**kw):
        if base not in ROUTES or not set(routes)<=ROUTES[base]:raise ValueError('OBSERVATION_ROUTE_FORBIDDEN')
        self.budget=budget;self.observations=[]
        super().__init__(base,routes,**kw)
    async def get_json(self,path,params=None,headers=None):
        if headers is not None or self.base not in ROUTES or path not in ROUTES[self.base] or path not in self.routes:raise ValueError('OBSERVATION_ROUTE_FORBIDDEN')
        async with self.budget.lock:
            await self.budget.before();started=time.time_ns()//1000000
            try:
                value=await super().get_json(path,params=params)
                self.observations.append(dict(endpoint=self.base+path,started_ms=started,received_ms=time.time_ns()//1000000,response_digest=digest(value)))
                return value
            finally:
                if self.audit and self.audit[-1].get('http_status')==429:self.budget.limited=True

async def bounded_pages(paginator,max_pages=2,max_items=200):
    rows=[];seen=set()
    for i in range(max_pages):
        page=await paginator.first_page()
        if type(page.has_more) is not bool:raise ValueError('PAGINATION_SHAPE')
        rows.extend(plain(x) for x in page.items)
        if len(rows)>max_items:raise ValueError('PAGE_ITEM_LIMIT')
        if not page.has_more:return rows,True,i+1
        cursor=page.next_cursor
        if not isinstance(cursor,str) or not cursor or cursor in seen:raise ValueError('PAGINATION_CURSOR')
        seen.add(cursor);paginator=paginator.from_cursor(cursor)
    return rows,False,max_pages

class ObservationAuthority:
    """Exact locally acquired fact envelopes; no positive unsupported checks.
    In-process acquisition provenance, NOT an external signed attestation.
    """
    def __init__(self,context):self.context=copy.deepcopy(context);self._records={}
    def record(self,check,payload,source_digest,observed_ms):
        if check not in ('market_identity_verified','wallet_account_identity_verified','clock_sanity'):raise ValueError('UNSUPPORTED_POSITIVE_CLAIM')
        row={**self.context,'check':check,'payload':copy.deepcopy(payload),'source_digest':digest(payload),'acquisition_digest':source_digest,'observed_ms':observed_ms,'valid_until_ms':observed_ms+5000,'provenance':'LOCAL_READ_ONLY_ACQUISITION_NOT_THIRD_PARTY_SIGNATURE'}
        self._records[digest(row)]=copy.deepcopy(row);return row
    def verify(self,row):return self._records.get(digest(row))==row
    def verify_client(self,client,record):return False  # observations do not qualify order transport
    def verify_bindings(self,bindings,proof):return False  # no custody readiness manufactured

class Collector:
    def __init__(self,client,public,gamma,*,wallet,signer,signature_type,budget,clock=lambda:time.time_ns()//1000000):
        self.client=client;self.public=public;self.gamma=gamma;self.wallet=wallet;self.signer=signer;self.signature_type=signature_type;self.budget=budget;self.clock=clock
        self.binding=(client,client.clob,client.data,public,gamma,wallet,signer,signature_type)
    def check_binding(self):
        if (self.client,self.client.clob,self.client.data,self.public,self.gamma,self.wallet,self.signer,self.signature_type)!=self.binding or self.client.wallet!=self.wallet or self.client.signature_type!=self.signature_type:raise ValueError('OBSERVATION_BINDING_CHANGED')
    async def collect(self,selection):
        self.check_binding();now=self.clock();start=now//300000*300;slug='btc-updown-5m-'+str(start)
        selectors=selection.get('selectors',{})
        explicit={r['value'] for k in ('MARKET_SLUG','POLYMARKET_MARKET_SLUG') for r in selectors.get(k,[])}
        if explicit and explicit!={slug}:raise ValueError('CONFIG_MARKET_NOT_CURRENT_V1_SLOT')
        report=dict(mode='LIVE_READ_ONLY_OBSERVATION',started_ms=now,account=self.wallet,signer=self.signer,signature_type=self.signature_type,market_policy=selection['market_policy'],checks={},proof_records=[],submit_allowed=False,ready_for_arm=False,current_inventory_proven=False)
        checks=report['checks'];rows={};market=None
        async def stage(name,op):
            stamp=self.clock()
            try:result=await asyncio.wait_for(op(),25)
            except Exception as exc:result=dict(status='BLOCKED',reason=type(exc).__name__)
            result.update(started_ms=stamp,finished_ms=self.clock());checks[name]=result
        async def clock_read():
            before=self.clock();server=await self.public.get_json('/time');after=self.clock()
            if type(server) is not int or abs(after-server*1000)>5000:raise ValueError('SERVER_CLOCK_UNQUALIFIED')
            return dict(status='OBSERVED',offset_ms=server*1000-(before+after)//2,uncertainty_ms=1000+(after-before)//2,server_seconds=server)
        await stage('clock',clock_read)
        async def market_read():
            nonlocal market
            values=await self.gamma.get_json('/markets',params={'slug':slug})
            from app.collectors.polymarket import PolymarketMarketDiscovery
            from app.d5.identity import MarketIdentity
            if not isinstance(values,list) or len(values)!=1:raise ValueError('MARKET_AMBIGUOUS')
            parsed=PolymarketMarketDiscovery.parse_market_list(values)
            if len(parsed)!=1:raise ValueError('MARKET_PARSE')
            market=MarketIdentity.from_market(parsed[0]);raw=values[0]
            if market.market_slug!=slug or market.expiry_ts_ms!=(start+300)*1000 or raw.get('closed') is not False or raw.get('active') is not True:raise ValueError('MARKET_EXPIRED_OR_INVALID')
            for key,actual in (('CONDITION_ID',market.condition_id),('TOKEN_UP',market.token_up),('TOKEN_DOWN',market.token_down)):
                if any(r['value']!=actual for r in selectors.get(key,[])):raise ValueError('CONFIG_MARKET_IDENTITY_CONFLICT')
            return dict(status='OBSERVED',**market.fields(),source_digest=digest(raw),valid_until_ms=market.expiry_ts_ms)
        await stage('market',market_read)
        async def balance_read():
            value=plain(await self.client.get_balance_allowance(asset_type='COLLATERAL'))
            from polymarket._internal.environment import PRODUCTION_CONFIG as env
            raw=dec(value['balance'])
            if raw!=raw.to_integral_value():raise ValueError('BALANCE_UNITS')
            allowances=[dec(v) for k,v in value['allowances'].items() if k.lower()==env.standard_exchange.lower()]
            if len(allowances)!=1:raise ValueError('ALLOWANCE_SPENDER')
            return dict(status='OBSERVED_AUTHENTICATED_GET',balance_raw=str(raw),allowance_raw=str(allowances[0]),units='BASE_UNITS',collateral_contract=env.collateral_token,scope='CREDENTIAL',atomic_frontier=None,complete=False)
        if checks['clock']['status']=='OBSERVED':await stage('balance',balance_read)
        else:checks['balance']=dict(status='BLOCKED',reason='CLOCK_PREFLIGHT')
        balance=checks['balance']
        checks['budget']=dict(status='BLOCKED',reason='BALANCE_OR_UNITS_NOT_QUALIFIED',required_experiment_budget='100')
        if balance.get('status')=='OBSERVED_AUTHENTICATED_GET' and (dec(balance['balance_raw'])==0 or dec(balance['allowance_raw'])==0):checks['budget']['reason']='OBSERVED_ZERO_CREDENTIAL_COLLATERAL_OR_ALLOWANCE'
        async def account_pages(kind):
            if kind=='trades':
                from .observed_trades import collect_scoped_trades
                summary,validated=await collect_scoped_trades(self.client,account=self.wallet,market=market.condition_id,tokens=(market.token_up,market.token_down),start_seconds=start,expiry_ms=market.expiry_ts_ms,clock=self.clock)
                if summary['status']=='OBSERVED_ATTRIBUTED':rows['trades']=validated
                else:rows.pop('trades',None)
                return summary
            from polymarket._internal.actions import account as a
            build=a.build_list_open_orders_request;parse=a.parse_open_orders_page;filters={}
            values,complete,pages=await bounded_pages(self.client._pages(lambda **kw:build(**filters,**kw),parse))
            ids=[v.get('id') for v in values]
            if any(type(i) is not str or not i for i in ids) or len(set(ids))!=len(ids):raise ValueError('DUPLICATE_ID')
            if kind=='orders' and any(str(v.get('maker_address','')).lower()!=self.wallet.lower() for v in values):raise ValueError('ORDER_ACCOUNT_IDENTITY')
            rows[kind]=values
            statuses={}
            return dict(status='OBSERVED',count=len(values),pages=pages,pagination_complete=complete,scope='CREDENTIAL_OPEN_ORDERS' if kind=='orders' else 'CREDENTIAL_SELECTED_MARKET_SINCE_SLOT_START',status_counts=statuses,complete=False,atomic_frontier=None,settlement_finality_proven=False,fee_effects_proven=False)
        if checks['balance']['status']=='OBSERVED_AUTHENTICATED_GET':
            await stage('orders',lambda:account_pages('orders'))
            if market and checks['market']['status']=='OBSERVED':await stage('trades',lambda:account_pages('trades'))
            else:checks['trades']=dict(status='BLOCKED',reason='MARKET_SELECTION')
        async def positions_read():
            values,complete,pages=await bounded_pages(self.client.list_positions(user=self.wallet,full_history=False,include_archived=False,filter_type='TOKENS',filter_amount=0))
            positions={}
            for v in values:
                token=str(v['asset_id'])
                if str(v['wallet']).lower()!=self.wallet.lower() or not token.isdecimal() or int(token)>=2**256 or token in positions:raise ValueError('POSITION_IDENTITY')
                positions[token]=str(dec(v['current_size']))
            rows['positions']=values
            return dict(status='OBSERVED_INDEX_ONLY',count=len(values),nonzero_positions={k:v for k,v in positions.items() if dec(v)},pages=pages,pagination_complete=complete,scope='INDEX_CURRENT_POSITIONS_NOT_GLOBAL',complete=False,atomic_frontier=None)
        await stage('positions',positions_read)
        async def fees_read():
            rates={}
            for token in (market.token_up,market.token_down):
                raw=await self.public.get_json('/fee-rate',params={'token_id':token})
                rate=raw.get('base_fee') if isinstance(raw,dict) else None
                if type(rate) not in (str,int) or not str(rate).isdigit():raise ValueError('FEE_RATE_SCHEMA')
                rates[token]=dict(base_fee=str(rate),response_digest=digest(raw))
            return dict(status='OBSERVED_RATE_ONLY',rates=rates,round_trip_upper_bound_proven=False,native_cash_share_effects_proven=False)
        if market and checks['market']['status']=='OBSERVED':await stage('fee_rates',fees_read)
        self.check_binding()
        report['finished_ms']=self.clock();report['observations_expired_for_arming']=True
        report['unknowns']=['COMMON_ATOMIC_FRONTIER','GLOBAL_WALLET_COMPLETENESS','POST_OBSERVATION_MUTATION_CLOSURE','FINAL_ATTRIBUTED_CASH_AND_SHARE_FEES','ROUND_TRIP_FEE_UPPER_BOUND','SDK_ORDER_TRANSPORT_QUALIFICATION','SPECIFIC_EXPOSURE_OPERATOR_ACCEPTANCE']
        txs=[]
        validated_trades=rows.get('trades',[]) if checks.get('trades',{}).get('status')=='OBSERVED_ATTRIBUTED' else []
        for v in validated_trades:
            tx=v.get('transaction_hash')
            if type(tx) is str and re.fullmatch('0x[0-9a-fA-F]{64}',tx) and tx not in txs:txs.append(tx)
        report['receipt_candidates']=txs[:2]
        report['receipt_candidate_scope']='ATTRIBUTED_RETURNED_TRADES_ONLY' if checks.get('trades',{}).get('status')=='OBSERVED_ATTRIBUTED' else 'BLOCKED_TRADE_SCOPE'
        if market and checks['market']['status']=='OBSERVED':
            from .v1_binding import verify
            context=dict(account=self.wallet,market=market.condition_id,session='readonly-'+str(now),collateral='pUSD',strategy_hashes=verify())
            self.authority=ObservationAuthority(context)
            m=checks['market'];payload=dict(condition=market.condition_id,tokens=[market.token_up,market.token_down],outcome_tokens={'UP':market.token_up,'DOWN':market.token_down},expires_ms=market.expiry_ts_ms)
            report['proof_records'].append(self.authority.record('market_identity_verified',payload,m['source_digest'],m['finished_ms']))
            if checks['balance']['status']=='OBSERVED_AUTHENTICATED_GET' and self.wallet.lower()==self.signer.lower() and self.signature_type==0:
                p=dict(wallet=self.wallet,maker=self.wallet,signer=self.signer)
                report['proof_records'].append(self.authority.record('wallet_account_identity_verified',p,self.client.clob.observations[0]['response_digest'],checks['balance']['finished_ms']))
        report['positive_records_scope']='LOCAL_HTTPS_ACQUISITION_ONLY_NOT_FULL_PREFLIGHT'
        return report

def build_collector(creds,wallet,signer,signature_type,*,budget=None):
    from polymarket._internal.hmac import build_hmac_signature
    budget=budget or ReadBudget();audit=[]
    authenticated=('/balance-allowance','/data/orders','/data/trades')
    async def headers(path):
        if path not in authenticated:raise ValueError('HMAC_ROUTE_FORBIDDEN')
        stamp=int(time.time())
        return {'POLY_ADDRESS':signer,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],'POLY_TIMESTAMP':str(stamp),'POLY_SIGNATURE':build_hmac_signature(secret=creds['secret'],timestamp=stamp,method='GET',path=path,body=None)}
    clob=ObservationGET('https://clob.polymarket.com',authenticated,budget=budget,headers=headers,audit=audit)
    data=ObservationGET('https://data-api.polymarket.com',('/v2/positions',),budget=budget,audit=audit)
    public=ObservationGET('https://clob.polymarket.com',('/time','/fee-rate'),budget=budget,audit=audit)
    gamma=ObservationGET('https://gamma-api.polymarket.com',('/markets',),budget=budget,audit=audit)
    client=ReadOnlyClient(wallet=wallet,signature_type=signature_type,clob=clob,data=data)
    result=Collector(client,public,gamma,wallet=wallet,signer=signer,signature_type=signature_type,budget=budget);result.audit=audit
    return result
