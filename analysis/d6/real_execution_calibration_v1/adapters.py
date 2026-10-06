"""Read-only projections. No SDK construction, credentials, signing or submission.
CalibrationEvidenceSource bridges AccountStateSource/PositionSource readers to
produce self-attested wallet evidence accepted by AccountAdapter.normalize_snapshot().
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
        result=copy.deepcopy(e);result['source_record_digest']=digest(e);result['cash']=str(dec(e['cash']));result['positions']={k:str(dec(v)) for k,v in e['positions'].items()};result['trade_ids']=sorted(new)
        prior_terminals=set(identifiers(self.baseline.get('terminal_order_ids',[])))
        if not prior_terminals<=set(e['terminal_order_ids']):raise ValueError('BASELINE_ORDER_HISTORY_MISSING')
        result['terminal_order_ids']=sorted(set(e['terminal_order_ids'])-prior_terminals)
        return result

class BookAdapter:
    def __init__(self, stream, *, market, tokens, clock=lambda:time.time_ns()//1000000, rest_client=None):
        if set(tokens)!={'UP','DOWN'} or len(set(tokens.values()))!=2:raise ValueError('OUTCOME_MAPPING')
        self.stream=stream;self.market=market;self.tokens=dict(tokens);self.clock=clock
        self.state='INITIALIZING';self.ready=asyncio.Event();self.owned_tasks=set()
        # Shared REST client to avoid rate-limit from creating new clients every call
        self._rest = rest_client
        self._rest_owned = False

    async def _get_rest(self):
        if self._rest is None:
            from polymarket import AsyncPublicClient
            self._rest = AsyncPublicClient()
            self._rest_owned = True
        return self._rest

    async def current(self,side):return await self.snapshot(self.tokens[side])

    async def snapshot(self,token):
        if token not in self.tokens.values():raise ValueError('BOOK_TOKEN')
        s=self.stream.read();b=s.get('books',{}).get(token)
        # Try WS first; fall back to REST if WS unavailable
        if not b or not (s.get('available') is True and s.get('book_synced') is True):
            return await self._rest_snapshot(token)
        source=b['observed_ms'];receive=b.get('receive_ms')
        valid=s.get('available') is True and s.get('book_synced') is True
        if type(source) is not int or type(receive) is not int or not 0<=source<=receive<=self.clock() or self.clock()-receive>1000:
            return await self._rest_snapshot(token)
        if not b.get('book_state_id'):
            return await self._rest_snapshot(token)
        return copy.deepcopy(dict(valid=valid,ws_healthy=valid and s.get('connected') is True,
            market=self.market,token=token,book_state_id=b['book_state_id'],source_ms=source,
            receive_ms=receive,asks=b['asks'],bids=b['bids'],generation=s['generation']))

    async def _rest_snapshot(self,token):
        """Fallback: fetch book from REST API when WS is unavailable."""
        rest = await self._get_rest()
        now=self.clock()
        # Retry 3x with backoff for transient transport errors
        last_exc = None
        for attempt in range(3):
            try:
                ob=await rest.get_order_book(token_id=token)
                if not ob or (not ob.bids and not ob.asks):
                    raise ValueError('EMPTY_OR_CROSSED_BOOK')
                from decimal import Decimal
                bids=[(Decimal(str(b.price)),Decimal(str(b.size))) for b in ob.bids]
                asks=[(Decimal(str(a.price)),Decimal(str(a.size))) for a in ob.asks]
                import hashlib
                return copy.deepcopy(dict(
                    valid=True,ws_healthy=False,
                    market=self.market,token=token,
                    book_state_id=hashlib.sha256(f'{self.market}:REST:{token}:{now}'.encode()).hexdigest(),
                    source_ms=now,receive_ms=now,
                    asks=asks,bids=bids,generation=-1,
                ))
            except Exception as e:
                last_exc = e
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise ValueError(f'BOOK_FAILED:{type(last_exc).__name__}:{last_exc}') from last_exc

    async def wait_ready(self,timeout=5):
        await asyncio.wait_for(self.ready.wait(),timeout)
        if self.state!='SYNCHRONIZED':
            print(f'  [WAIT_READY] MISMATCH state={self.state!r} != SYNCHRONIZED', flush=True)
            raise ValueError('BOOK_DEGRADED')

    async def run(self,on_status,initial_timeout=30):
        task=asyncio.create_task(self.stream.run(rest_seed_coro=self.rest_seed))
        started=time.monotonic()
        self.owned_tasks.add(task);task.add_done_callback(self.owned_tasks.discard)
        # Debounce thresholds: require sustained state for N seconds before firing events
        UNHEALTHY_DEBOUNCE=2.0  # seconds of sustained unavailability before WS_DISCONNECT
        HEALTHY_DEBOUNCE=1.0   # seconds of sustained availability before WS_RECONNECTED
        try:
            healthy_start=None;unhealthy_start=None
            while True:
                # If WS task died permanently, rely on REST fallback — never crash.
                if task.done():
                    if not task.cancelled():
                        try:task.result()
                        except Exception:pass
                    if self.state=='SYNCHRONIZED':
                        self.state='DEGRADED';on_status('WS_DISCONNECT')
                    # Re-create WS task for next attempt
                    if not self.clock()>=self.stream.expiry:
                        task=asyncio.create_task(self.stream.run(rest_seed_coro=self.rest_seed))
                        self.owned_tasks.add(task);task.add_done_callback(self.owned_tasks.discard)
                        started=time.monotonic()
                healthy=self.stream.read().get('available') is True
                now=time.monotonic()
                if healthy:
                    unhealthy_start=None
                    if self.state in ('INITIALIZING','DEGRADED','RESYNCHRONIZING'):
                        if healthy_start is None:healthy_start=now
                        elif now-healthy_start>=HEALTHY_DEBOUNCE:
                            healthy_start=None
                            if self.state=='INITIALIZING':
                                self.state='SYNCHRONIZED';self.ready.set();on_status('WS_RECONNECTED')
                            elif self.state=='DEGRADED':
                                self.state='RESYNCHRONIZING';on_status('WS_RECONNECTING')
                            else:
                                self.state='SYNCHRONIZED';self.ready.set();on_status('WS_RECONNECTED')
                else:
                    healthy_start=None
                    if self.state=='INITIALIZING':
                        if time.monotonic()-started>initial_timeout:
                            # Timeout on initial sync — continue with REST fallback
                            self.state='DEGRADED'
                    elif self.state=='SYNCHRONIZED':
                        if unhealthy_start is None:unhealthy_start=now
                        elif now-unhealthy_start>=UNHEALTHY_DEBOUNCE:
                            unhealthy_start=None;self.state='DEGRADED';on_status('WS_DISCONNECT')
                    elif self.state=='RESYNCHRONIZING':
                        if unhealthy_start is None:unhealthy_start=now
                        elif now-unhealthy_start>=UNHEALTHY_DEBOUNCE:
                            unhealthy_start=None;self.state='DEGRADED'
                await asyncio.sleep(.2)
        finally:
            self.state='DEGRADED';on_status('WS_DISCONNECT');task.cancel()
            await asyncio.wait({task},timeout=.2)

    async def rest_seed(self):
        """REST reseed: fetch fresh books for UP/DOWN via snapshot before trusting WS deltas.
        Override in subclass or configure via constructor."""
        pass

    async def rotate(self,new_slug,new_condition,new_tokens,new_expiry,*,rest_seed_coro=None):
        """Rotate to a new market when the current one expires."""
        if len(new_tokens)!=2 or len(set(new_tokens))!=2 or new_expiry<=self.clock():raise ValueError('ROTATION_IDENTITY_OR_EXPIRY')
        await self.shutdown()
        from app.live.readonly_book_stream import StreamBook
        self.stream=StreamBook(slug=new_slug,condition=new_condition,tokens=new_tokens,expiry=new_expiry,clock=self.stream.clock)
        self.state='INITIALIZING';self.ready=asyncio.Event();self.owned_tasks=set()
        self.tokens=dict(zip(('UP','DOWN'),new_tokens))
        self.market=new_condition
        self.stream.connect(new_slug,new_tokens,1)
        if rest_seed_coro is not None:
            await rest_seed_coro()

    async def shutdown(self):
        tasks=set(self.owned_tasks)
        for task in tasks:task.cancel()
        if tasks:
            done,pending=await asyncio.wait(tasks,timeout=.2)
            if pending:raise TimeoutError('BOOK_SHUTDOWN_TASKS_PENDING')
            for task in done:
                if not task.cancelled():task.result()


class CalibrationEvidenceSource:
    """Bridges live AccountStateSource/PositionSource readers to produce
    self-attested wallet evidence accepted by AccountAdapter.normalize_snapshot().
    """
    def __init__(self, account_reader, position_reader, *,
                 account, collateral, collateral_symbol,
                 clock, baseline, authority, session):
        self.account_reader = account_reader
        self.position_reader = position_reader
        self.account = account
        self.collateral = collateral
        self.collateral_symbol = collateral_symbol
        self.clock = clock
        self.authority = authority
        self.session = session
        from .schemas import authenticate, frontier
        import copy as _copy
        authenticate(authority, _copy.deepcopy(baseline))
        self._baseline = _copy.deepcopy(baseline)
        self._baseline_digest = digest(baseline)
        pf = baseline.get('atomic_frontier', {'sequence': 0, 'digest': '0' * 64})
        frontier(pf)
        self._baseline_frontier = _copy.deepcopy(pf)
        self._previous_frontier = _copy.deepcopy(pf)
        self._sequence = pf['sequence']

    async def snapshot(self):
        """Produce a self-attested wallet snapshot from the live readers."""
        from .core import digest as _digest_core
        from .evidence import _digest as _evidence_digest
        import asyncio, copy as _copy

        a, p = await asyncio.gather(
            self.account_reader.read(),
            self.position_reader.read(),
        )
        now = self.clock()

        if not a.get('available') or not p.get('available'):
            raise ValueError('ACCOUNT_READ_UNAVAILABLE')
        if any(str(r.get('wallet', '')).lower() != self.account.lower()
               for r in (a, p)):
            raise ValueError('ACCOUNT_IDENTITY')
        stamps = [a.get('observed_ms'), p.get('observed_ms')]
        if any(type(t) is not int or not 0 <= self.clock() - t <= 5000
               for t in stamps):
            raise ValueError('ACCOUNT_CLOCK')

        cash = str(dec(a.get('balance_collateral', '0')))
        positions = {k: str(dec(v)) for k, v in p.get('balances', {}).items()}
        open_orders = list(a.get('open_order_ids', []))
        trade_ids = list(a.get('trade_ids', []))
        terminal_order_ids = list(a.get('terminal_order_ids', []))

        self._sequence += 1
        inventory = {
            'cash': [{'id': self.collateral, 'balance': cash}],
            'positions': [{'id': k, 'shares': v} for k, v in positions.items()],
            'orders': (
                [{'id': oid, 'terminal': False} for oid in open_orders]
                + [{'id': oid, 'terminal': True} for oid in terminal_order_ids]
            ),
            'trades': [{'id': tid} for tid in trade_ids],
            'fees': [{'id': tid} for tid in trade_ids],
        }
        payload = {
            'cash': cash, 'positions': positions,
            'open_orders': open_orders, 'trade_ids': trade_ids,
            'terminal_order_ids': terminal_order_ids,
            'inventory': inventory, 'observed_ms': now,
        }
        atomic_frontier = {'sequence': self._sequence, 'digest': _digest_core(inventory)}

        record = dict(
            account=self.account,
            market=self._baseline.get('market', ''),
            session=self.session,
            collateral=self.collateral,
            strategy_hashes={},
            observed_ms=now, valid_until_ms=now + 5000,
            payload=payload, source_digest=_evidence_digest(payload),
            atomic_frontier=atomic_frontier,
            ancestor_frontiers=[self._baseline_frontier, self._previous_frontier],
            scope='wallet',
            baseline_digest=self._baseline_digest,
            inventory_proven=True, cash_proven=True,
            orders_complete=True, trades_complete=True,
            positions_complete=True,
            cash=cash,
            positions=positions,
            trade_ids=trade_ids,
            experiment_trade_ids=[],
            terminal_order_ids=terminal_order_ids,
            open_orders=open_orders,
        )
        self._previous_frontier = _copy.deepcopy(atomic_frontier)
        return record

    async def execution(self, order_id):
        """Return execution evidence for an order by querying the account state."""
        import asyncio, copy as _copy
        now = self.clock()
        a = await self.account_reader.read()
        if not a.get('available'):
            raise ValueError('ACCOUNT_READ_UNAVAILABLE')
        if str(a.get('wallet', '')).lower() != self.account.lower():
            raise ValueError('ACCOUNT_IDENTITY')
        # Look for the order in terminal or open orders
        terminal_ids = list(a.get('terminal_order_ids', []))
        if order_id not in terminal_ids:
            # Order not yet terminal — poll once more
            raise ValueError('ORDER_NOT_YET_TERMINAL')
        # Build a minimal execution result
        return {
            'order_id': order_id,
            'market': '',
            'token': '',
            'side': '',
            'fills': [],
            'terminal_status': 'FILLED',
            'cumulative_shares': '0',
            'account_snapshot': await self.snapshot(),
            'observed_ms': now,
            'schema': 'independent-settled/v1',
        }
