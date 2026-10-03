"""Authenticated full-wallet observations. Never infer completeness from scoped reads.

The approved provider is an external trust boundary. A signature authenticates
its claims; it does not establish that the provider audited the entire wallet.
The authority trust policy and provider coverage must be approved independently.
"""
import copy,asyncio
from .core import digest
from .schemas import authenticate, frontier, integer, identifiers

COMPONENTS = frozenset(('cash', 'positions', 'orders', 'trades', 'fees'))

class ProductionEvidenceSource:
    def __init__(self, provider, *, authority, account, collateral, session, baseline, clock):
        from .production_authority import ProductionAuthority
        if type(authority) is not ProductionAuthority:
            raise ValueError('PRODUCTION_AUTHORITY_REQUIRED')
        self.provider=provider; self.authority=authority; self.account=account
        self.collateral=collateral; self.session=session; self.clock=clock
        self.baseline=copy.deepcopy(baseline); self.previous=None; self._lock=asyncio.Lock()
        self._validate(self.baseline, 'baseline', baseline=True)

    def _validate(self, record, kind, *, baseline=False):
        if not self.authority.verify_provenance(record):raise ValueError('AUTHORITY_REJECTED')
        if record.get('kind') != kind: raise ValueError('EVIDENCE_KIND')
        if any(record.get(k)!=v for k,v in dict(account=self.account,collateral=self.collateral,session=self.session,scope='wallet').items()):
            raise ValueError('EVIDENCE_SCOPE')
        now=self.clock()
        if not 0 <= now-integer(record['observed_ms']) <= 5000 or integer(record['valid_until_ms']) < now:
            raise ValueError('ACCOUNT_CLOCK')
        lifetime=259200000 if baseline else 5000
        if record['valid_until_ms']>record['observed_ms']+lifetime:raise ValueError('EVIDENCE_VALIDITY_WINDOW')
        f=frontier(record['atomic_frontier'])
        if f['digest']!=digest(record['inventory']):raise ValueError('FRONTIER_CONTENT')
        coverage=record['coverage']
        if set(coverage)!=COMPONENTS: raise ValueError('COVERAGE_COMPONENTS')
        for name, proof in coverage.items():
            if proof.get('scope')!='wallet' or proof.get('filters')!={} or proof.get('frontier')!=f:
                raise ValueError('COVERAGE_SCOPE_OR_FRONTIER')
            if proof.get('complete') is not True or proof.get('next_cursor') is not None or proof.get('origin')!='wallet_creation':
                raise ValueError('COVERAGE_INCOMPLETE')
            rows=record['inventory'][name]
            if type(rows) is not list or integer(proof['count'])!=len(rows) or proof['digest']!=digest(rows):
                raise ValueError('COVERAGE_CONTENT')
            identifiers([r['id'] for r in rows])
        if not baseline:
            if record.get('baseline_digest')!=digest(self.baseline): raise ValueError('BASELINE_BINDING')
            ancestors=record.get('ancestor_frontiers',[])
            for ancestor in (self.baseline['atomic_frontier'], self.previous):
                if ancestor is None: continue
                if f['sequence'] < ancestor['sequence'] or (f['sequence']==ancestor['sequence'] and f!=ancestor):
                    raise ValueError('EVIDENCE_FORK_OR_REPLAY')
                if f!=ancestor and ancestor not in ancestors: raise ValueError('EVIDENCE_LINEAGE')
        for key in ('inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete'):
            if record.get(key) is not True: raise ValueError('COMPLETENESS_UNPROVEN')
        # Bind adapter projections to the authenticated inventory, never just flags.
        inv=record['inventory']
        if inv['cash'] != [dict(id=self.collateral, balance=record['cash'])]: raise ValueError('CASH_PROJECTION')
        if {r['id']:r['shares'] for r in inv['positions']}!=record['positions']: raise ValueError('POSITION_PROJECTION')
        if [r['id'] for r in inv['trades']]!=record['trade_ids']: raise ValueError('TRADE_PROJECTION')
        if [r['id'] for r in inv['orders'] if r['terminal'] is False]!=record['open_orders']: raise ValueError('ORDER_PROJECTION')
        if [r['id'] for r in inv['orders'] if r['terminal'] is True]!=record['terminal_order_ids']: raise ValueError('TERMINAL_PROJECTION')
        if any(type(r['terminal']) is not bool for r in inv['orders']): raise ValueError('ORDER_TERMINAL_SCHEMA')
        if {r['id'] for r in inv['fees']} != set(record['trade_ids']): raise ValueError('FEE_COVERAGE')
        self.previous=copy.deepcopy(f)
        return copy.deepcopy(record)

    async def snapshot(self):
        async with self._lock:
            return self._validate(await asyncio.wait_for(self.provider.snapshot(),timeout=5), 'snapshot')

    async def execution(self, order_id):
        async with self._lock:
            record=copy.deepcopy(await asyncio.wait_for(self.provider.execution(order_id),timeout=5))
            authenticate(self.authority,record)
            if record.get('kind')!='execution' or record.get('order_id')!=order_id:
                raise ValueError('EXECUTION_BINDING')
            post=self._validate(record['account_snapshot'], 'snapshot')
            fees={r['id']:r for r in post['inventory']['fees']}
            trades={r['id']:r for r in post['inventory']['trades']}
            for fill in record['fills']:
                tid=fill['trade_id']
                if fill['order_id']!=order_id or trades.get(tid,{}).get('fill')!=fill:
                    raise ValueError('FILL_PROJECTION')
                if any(fees.get(tid,{}).get(k)!=fill[k] for k in ('cash_fee','share_fee')):
                    raise ValueError('FEE_PROJECTION')
            if {r['id'] for r in trades.values() if r['fill']['order_id']==order_id}!={f['trade_id'] for f in record['fills']}:
                raise ValueError('EXECUTION_INCOMPLETE')
            return record
