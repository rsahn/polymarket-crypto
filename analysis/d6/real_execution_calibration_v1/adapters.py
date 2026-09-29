"""Read-only projections. No SDK construction, credentials, signing or submission.
Current credential/enumerated-asset readers cannot prove wallet completeness.
Consequently account execution remains blocked rather than manufacturing proofs.
"""
import asyncio
import copy
import time
from .core import dec, digest
from .schemas import authenticate,frontier,integer,identifiers

class AccountAdapter:
    def __init__(self, account_reader, position_reader, *, account, collateral=None, evidence_source=None, authority=None, baseline=None, session=None, intents=None, clock=lambda:time.time_ns()//1000000):
        self.account_reader=account_reader; self.position_reader=position_reader
        self.account=account; self.clock=clock;self.collateral=collateral
        self.evidence_source=evidence_source;self.authority=authority;self.baseline=baseline;self.session=session;self.intents=intents

    async def snapshot(self):
        if self.evidence_source is not None:return self.normalize_snapshot(await self.evidence_source.snapshot())
        a,p=await asyncio.gather(self.account_reader.read(),self.position_reader.read())
        if not a.get('available') or not p.get('available'):raise ValueError('ACCOUNT_READ_UNAVAILABLE')
        if any(str(r.get('wallet','')).lower()!=self.account.lower() for r in (a,p)):raise ValueError('ACCOUNT_IDENTITY')
        if self.collateral is None or any(r.get('collateral_symbol')!=self.collateral for r in (a,p)):raise ValueError('COLLATERAL_IDENTITY')
        stamps=[a.get('observed_ms'),p.get('observed_ms')]
        if any(type(t) is not int or not 0<=self.clock()-t<=5000 for t in stamps):raise ValueError('ACCOUNT_CLOCK')
        return dict(account=self.account, observed_ms=min(stamps),cash=str(dec(a['balance_collateral'])),
                    positions={k:str(dec(v)) for k,v in p['balances'].items()},
                    open_orders=copy.deepcopy(a['open_order_ids']),trade_ids=copy.deepcopy(a.get('trade_ids',[])),
                    terminal_order_ids=[],inventory_proven=False,cash_proven=False,orders_complete=False,
                    trades_complete=False,positions_complete=False,
                    blockers=['FULL_WALLET_SCOPE_UNPROVEN','GLOBAL_INVENTORY_ATOMICITY_UNPROVEN',
                              'COLLATERAL_AND_FEE_EFFECTS_UNQUALIFIED','EXPERIMENT_BASELINE_UNQUALIFIED'],
                    provenance={'account_scope':a.get('scope'),'positions_scope':p.get('scope'),
                                'account_digest':digest(a),'positions_digest':digest(p)})

    async def execution(self,order_id):
        if not isinstance(order_id,str) or not order_id:raise ValueError('ORDER_ID_REQUIRED')
        if self.evidence_source is None:raise ValueError('AUTHORITATIVE_FILLS_FEES_AND_ACCOUNT_SCOPE_UNQUALIFIED')
        e=await self.evidence_source.execution(order_id);self.verify_observation(e)
        if e.get('order_id')!=order_id:raise ValueError('EXECUTION_ORDER_IDENTITY')
        if self.intents is None:raise ValueError('LOCAL_INTENTS_REQUIRED')
        expected=[o for o in self.intents().values() if o.get('order_id')==order_id]
        if len(expected)!=1 or any(e.get(k)!=expected[0][k] for k in ('market','token','side')):raise ValueError('EXECUTION_INTENT_IDENTITY')
        if e.get('schema')=='polymarket-client/0.11.0':
            from .raw_trades import normalize_trade
            if self.intents is None:raise ValueError('LOCAL_INTENTS_REQUIRED')
            matches=[o for o in self.intents().values() if o.get('order_id')==order_id]
            if len(matches)!=1:raise ValueError('LOCAL_INTENT_AMBIGUOUS')
            if type(e['raw_trades']) is not list:raise ValueError('RAW_TRADE_LIST')
            fills=[normalize_trade(r,matches[0],e['effects'][r['id']],self.authority,account=self.account,session=self.session,receive_ms=e['observed_ms']) for r in e['raw_trades']]
        elif e.get('schema')=='independent-settled/v1':fills=copy.deepcopy(e['fills'])
        else:raise ValueError('EXECUTION_SCHEMA_UNQUALIFIED')
        seen=set();total=dec(0)
        for f in fills:
            if f['trade_id'] in seen or f['order_id']!=order_id or f['market']!=e['market'] or f['side'] not in ('BUY','SELL'):raise ValueError('FILL_IDENTITY')
            seen.add(f['trade_id']);total+=dec(f['shares'])
            if not 0<dec(f['price'])<1 or dec(f['shares'])<=0:raise ValueError('FILL_AMOUNT')
            for k in ('cash_fee','share_fee'):f[k]=str(dec(f[k]))
            if f['fee_evidence'].get('cash_effect_proven') is not True or f['fee_evidence'].get('share_effect_proven') is not True:raise ValueError('FEE_EFFECT_UNPROVEN')
            integer(f['exchange_ts_ms']);integer(f['receive_ts_ms'])
            if not 0<=f['exchange_ts_ms']<=f['receive_ts_ms']<=self.clock():raise ValueError('FILL_CLOCK')
        if e['terminal_status'] not in ('FILLED','CANCELED','EXPIRED') or dec(e['cumulative_shares'])!=total:raise ValueError('TERMINAL_FILL_MISMATCH')
        if any(e['account_snapshot']['observed_ms']<f['receive_ts_ms'] for f in fills):raise ValueError('POST_FILL_SNAPSHOT_STALE')
        self.check_lineage(e['atomic_frontier'],e['account_snapshot'])
        return dict(fills=fills,terminal_status=e['terminal_status'],cumulative_shares=str(total),account_snapshot=self.normalize_snapshot(e['account_snapshot']))

    def verify_observation(self,e):
        if self.authority is None:raise ValueError('INDEPENDENT_ACCOUNT_PROOF_REQUIRED')
        authenticate(self.authority,copy.deepcopy(e))
        if not self.session or e.get('session')!=self.session:raise ValueError('ACCOUNT_SESSION')
        if e.get('account')!=self.account or e.get('collateral')!=self.collateral:raise ValueError('ACCOUNT_OR_COLLATERAL_IDENTITY')
        if e.get('scope')!='wallet':raise ValueError('PARTIAL_SCOPE')
        frontier(e.get('atomic_frontier'))
        if type(e.get('observed_ms')) is not int or not 0<=self.clock()-e['observed_ms']<=5000:raise ValueError('ACCOUNT_CLOCK')
        if not self.baseline:raise ValueError('BASELINE_UNVERIFIED')
        authenticate(self.authority,copy.deepcopy(self.baseline))
        if self.baseline.get('session')!=self.session or self.baseline.get('collateral')!=self.collateral:raise ValueError('BASELINE_CONTEXT')
        frontier(self.baseline.get('atomic_frontier'))
        self.check_lineage(self.baseline['atomic_frontier'],e)
        identifiers(self.baseline['trade_ids']);integer(self.baseline['valid_until_ms'])
        if self.baseline['account']!=self.account or self.baseline['valid_until_ms']<self.clock() or e.get('baseline_digest')!=digest(self.baseline):raise ValueError('BASELINE_STALE_OR_MISMATCH')

    @staticmethod
    def check_lineage(previous,observation):
        current=frontier(observation.get('atomic_frontier'))
        if current['sequence']<previous['sequence']:raise ValueError('FRONTIER_REGRESSION')
        if current['sequence']==previous['sequence']:
            if current['digest']!=previous['digest']:raise ValueError('FRONTIER_FORK')
        elif previous not in observation.get('ancestor_frontiers',[]):raise ValueError('FRONTIER_LINEAGE_UNPROVEN')

    def normalize_snapshot(self,e):
        self.verify_observation(e)
        for k in ('trade_ids','experiment_trade_ids','terminal_order_ids','open_orders'):identifiers(e[k])
        baseline=set(self.baseline['trade_ids']);all_ids=set(e['trade_ids'])
        if not baseline<=all_ids:raise ValueError('BASELINE_HISTORY_MISSING')
        new=all_ids-baseline
        if new!=set(e['experiment_trade_ids']):raise ValueError('FOREIGN_ACCOUNT_ACTIVITY')
        if e.get('foreign_order_ids'):raise ValueError('FOREIGN_ACCOUNT_ACTIVITY')
        if any(e.get(k) is not True for k in ('inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete')):raise ValueError('ACCOUNT_SCOPE_UNPROVEN')
        result=copy.deepcopy(e);result['cash']=str(dec(e['cash']));result['positions']={k:str(dec(v)) for k,v in e['positions'].items()};result['trade_ids']=sorted(new)
        return result

class BookAdapter:
    def __init__(self, stream, *, market, tokens, clock=lambda:time.time_ns()//1000000):
        if set(tokens)!={'UP','DOWN'} or len(set(tokens.values()))!=2:raise ValueError('OUTCOME_MAPPING')
        self.stream=stream;self.market=market;self.tokens=dict(tokens);self.clock=clock
        self.state='INITIALIZING';self.ready=asyncio.Event();self.owned_tasks=set()

    async def current(self,side):return await self.snapshot(self.tokens[side])

    async def snapshot(self,token):
        if token not in self.tokens.values():raise ValueError('BOOK_TOKEN')
        s=self.stream.read();b=s.get('books',{}).get(token)
        if not b or self.stream.condition!=self.market:raise ValueError('BOOK_IDENTITY_OR_MISSING')
        source=b['observed_ms'];receive=b.get('receive_ms')
        valid=s.get('available') is True and s.get('book_synced') is True
        if type(source) is not int or type(receive) is not int or not 0<=source<=receive<=self.clock() or self.clock()-receive>1000:
            raise ValueError('BOOK_CAUSAL_CLOCK_UNPROVEN')
        if not b.get('book_state_id'):raise ValueError('BOOK_CAUSAL_ID_UNPROVEN')
        return copy.deepcopy(dict(valid=valid,ws_healthy=valid and s.get('connected') is True,
            market=self.market,token=token,book_state_id=b['book_state_id'],source_ms=source,
            receive_ms=receive,asks=b['asks'],bids=b['bids'],generation=s['generation']))

    async def wait_ready(self,timeout=5):
        await asyncio.wait_for(self.ready.wait(),timeout)
        if self.state!='SYNCHRONIZED':raise ValueError('BOOK_DEGRADED')

    async def run(self,on_status,initial_timeout=30):
        task=asyncio.create_task(self.stream.run(rest_seed_coro=self.rest_seed));started=time.monotonic()
        self.owned_tasks.add(task);task.add_done_callback(self.owned_tasks.discard)
        try:
            while not task.done():
                healthy=self.stream.read().get('available') is True
                if self.state=='INITIALIZING':
                    if healthy:self.state='SYNCHRONIZED';self.ready.set();on_status('WS_RECONNECTED')
                    elif time.monotonic()-started>initial_timeout:raise TimeoutError('BOOK_INITIAL_SYNC_TIMEOUT')
                elif self.state=='SYNCHRONIZED' and not healthy:
                    self.state='DEGRADED';on_status('WS_DISCONNECT')
                elif self.state=='DEGRADED' and healthy:
                    self.state='RESYNCHRONIZING';on_status('WS_RECONNECTING')
                elif self.state=='RESYNCHRONIZING' and healthy:
                    self.state='SYNCHRONIZED';self.ready.set();on_status('WS_RECONNECTED')
                await asyncio.sleep(.02)
            await task
            raise RuntimeError('BOOK_STREAM_ENDED')
        finally:
            self.state='DEGRADED';on_status('WS_DISCONNECT');task.cancel()
            await asyncio.wait({task},timeout=.2)

    async def rest_seed(self):
        """REST reseed: fetch fresh books for UP/DOWN via snapshot before trusting WS deltas.
        Override in subclass or configure via constructor."""
        pass

    async def rotate(self,new_slug,new_condition,new_tokens,new_expiry,*,rest_seed_coro=None):
        """Rotate to a new market when the current one expires."""
        await self.shutdown()
        from .readonly_book_stream import StreamBook
        self.stream=StreamBook(slug=new_slug,condition=new_condition,tokens=new_tokens,expiry=new_expiry,clock=self.stream.clock)
        self.state='INITIALIZING';self.ready=asyncio.Event();self.owned_tasks=set()
        self.tokens=dict(zip(('UP','DOWN'),new_tokens))
        self.market=new_condition
        self.stream.connect(new_slug,new_tokens,1)
        if rest_seed_coro is not None:
            try:await rest_seed_coro()
            except Exception:pass

    async def shutdown(self):
        for task in self.owned_tasks:task.cancel()
        while self.owned_tasks:
            try:await asyncio.wait(set(self.owned_tasks),timeout=.1)
            except asyncio.CancelledError:continue
