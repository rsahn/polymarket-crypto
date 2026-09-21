"""Deterministic offline PAPER replay of D5 only. No strategy discovery."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .features import BTCFeatures
from .identity import MarketIdentity, assert_shadow
from .store import decode, encode


@dataclass
class Inventory:
    up_qty: float = 0.
    down_qty: float = 0.
    up_cost: float = 0.
    down_cost: float = 0.
    realized_pnl: float = 0.
    expired: bool = False

    @property
    def paired_qty(self):
        return min(self.up_qty,self.down_qty)

    @property
    def directional_up(self):
        return max(0.,self.up_qty-self.down_qty)

    @property
    def directional_down(self):
        return max(0.,self.down_qty-self.up_qty)

    @property
    def average_up_cost(self):
        return self.up_cost/self.up_qty if self.up_qty else 0.

    @property
    def average_down_cost(self):
        return self.down_cost/self.down_qty if self.down_qty else 0.

    @property
    def paired_cost_basis(self):
        return self.paired_qty*(self.average_up_cost+self.average_down_cost)

    def state(self):
        return {**asdict(self),'paired_qty':self.paired_qty,'directional_up':self.directional_up,
                'directional_down':self.directional_down,'average_up_cost':self.average_up_cost,
                'average_down_cost':self.average_down_cost,'paired_cost_basis':self.paired_cost_basis,
                'unrealized_pnl':None if abs(self.up_qty-self.down_qty)>1e-9 else
                                  self.paired_qty-self.up_cost-self.down_cost,
                'status':'UNRESOLVED_DIRECTIONAL_EXPOSURE' if abs(self.up_qty-self.down_qty)>1e-9 else
                         'PAIRED_AWAITING_SETTLEMENT' if self.paired_qty else 'FLAT'}


@dataclass(frozen=True)
class Decision:
    action: str = 'NO_TRADE'
    requested_qty: float = 0.
    reason: str = 'NO_VALIDATED_STRATEGY'


class Strategy(Protocol):
    def on_event(self, context: dict) -> Decision: ...


class NoTrade:
    def on_event(self, context):
        return Decision()


class DemoAlternating:
    """Infrastructure fixture only; never selected by live, no profitability claim."""
    def __init__(self):
        self.count = {}

    def on_event(self, context):
        if context['kind']!='BOOK':
            return Decision('WAIT')
        key = context['identity']['market_slug']
        n = self.count.get(key,0)
        self.count[key] = n+1
        return Decision(('BUY_UP','BUY_DOWN','REDUCE_UP','REDUCE_DOWN')[n%4],1.,'INFRASTRUCTURE_TEST')


class PaperExecutor:
    """Shares, visible depth, average-cost inventory. All fees included in cost basis."""
    def __init__(self, capital=500., fee_rate=0., friction_per_share=0., slippage=0.):
        assert_shadow()
        if not all(math.isfinite(x) and x>=0 for x in (capital,fee_rate,friction_per_share,slippage)) or capital<=0:
            raise ValueError('Invalid PAPER config')
        self.initial_capital = self.cash = capital
        self.reserved_cash = 0.
        self.fee_rate,self.friction,self.slippage = fee_rate,friction_per_share,slippage
        self.positions,self.identities,self.books,self.depth = {},{},{},{}
        self.orders,self.fills = [],[]
        self.fees = self.slippage_paid = self.turnover = 0.
        self.up_bought = self.down_bought = 0.
        self.pairs_created = self.pair_cost_sum = self.pairs_below_one = 0.

    def update_book(self, identity, book):
        if not identity.matches(book):
            raise ValueError('CROSS_MARKET_REJECT')
        key=identity.key
        if key in self.identities and self.identities[key]!=identity:
            raise ValueError('CROSS_MARKET_REJECT')
        self.identities[key]=identity
        self.positions.setdefault(key,Inventory())
        self.books[key]=book
        for side in ('UP','DOWN'):
            q=book[side.lower()]
            for ladder,pricekey,qtykey in [('asks','ask','ask_qty'),('bids','bid','bid_qty')]:
                levels=q.get(ladder) or ([(q[pricekey],q[qtykey])] if q.get(pricekey) is not None else [])
                visible={float(p):float(n) for p,n in levels if n>0 and math.isfinite(p) and math.isfinite(n)}
                old=self.depth.get((key,side,ladder),{})
                # No replenishment assumed when displayed quantity is unchanged.
                self.depth[key,side,ladder]={p:(n,max(0.,min(n,old[p][1]+n-old[p][0]))) if p in old else (n,n)
                                            for p,n in visible.items()}

    def execute(self, identity, decision, now, event_id):
        action=decision.action
        if action in ('NO_TRADE','WAIT'):
            return []
        if action not in ('BUY_UP','BUY_DOWN','REDUCE_UP','REDUCE_DOWN','PAIR'):
            raise ValueError('Unsupported action')
        requested=decision.requested_qty
        if not math.isfinite(requested) or requested<=0:
            raise ValueError('Order size must be positive finite SHARES')
        key=identity.key
        p=self.positions.setdefault(key,Inventory())
        if action=='PAIR':
            side='DOWN' if p.up_qty>p.down_qty else 'UP'
            requested=min(requested,abs(p.up_qty-p.down_qty))
            buy=True
        else:
            side='UP' if action.endswith('_UP') else 'DOWN'
            buy=action.startswith('BUY')
        order={'event_id':event_id,'market_slug':identity.market_slug,'condition_id':identity.condition_id,
               'token_id':identity.token(side),'action':action,'requested_qty':decision.requested_qty,
               'available_qty':0.,'fill_qty':0.,'status':'NO_FILL','reason':decision.reason}
        self.orders.append(order)
        book=self.books.get(key)
        if not book or self.identities.get(key)!=identity or p.expired or now>=identity.expiry_ts_ms:
            order['reason']='EXPIRED_OR_MISSING_BOOK'
            return []
        ladder='asks' if buy else 'bids'
        levels=self.depth.get((key,side,ladder),{})
        order['available_qty']=sum(n[1] for n in levels.values())
        attr=side.lower()
        requested=min(requested,getattr(p,attr+'_qty')) if not buy else requested
        result=[]
        before_pairs=p.paired_qty
        for px in sorted(levels,reverse=not buy):
            shown,remaining=levels[px]
            price=min(1.,px+self.slippage) if buy else max(0.,px-self.slippage)
            fee_unit=price*self.fee_rate+self.friction
            unit=price+fee_unit
            qty=min(requested-sum(f['fill_qty'] for f in result),remaining)
            if buy:
                qty=min(qty,max(0.,self.cash-self.reserved_cash)/unit) if unit>0 else 0.
            elif price<fee_unit:
                qty=0.
            if qty<=1e-12:
                continue
            fee=qty*fee_unit
            notional=qty*price
            if buy:
                self.reserved_cash=notional+fee
                self.cash-=self.reserved_cash
                self.reserved_cash=0.
                setattr(p,attr+'_qty',getattr(p,attr+'_qty')+qty)
                setattr(p,attr+'_cost',getattr(p,attr+'_cost')+notional+fee)
                if side=='UP': self.up_bought+=qty
                else: self.down_bought+=qty
            else:
                cost=getattr(p,attr+'_cost')*qty/getattr(p,attr+'_qty')
                self.cash+=notional-fee
                p.realized_pnl+=notional-fee-cost
                setattr(p,attr+'_qty',max(0.,getattr(p,attr+'_qty')-qty))
                setattr(p,attr+'_cost',max(0.,getattr(p,attr+'_cost')-cost))
            levels[px]=(shown,remaining-qty)
            slip=qty*abs(price-px)
            self.fees+=fee
            self.slippage_paid+=slip
            self.turnover+=notional
            fill={**order,'side':side,'buy':buy,'fill_qty':qty,'price':price,'fee':fee,
                  'slippage':slip,'notional':notional,'timestamp_ms':now,'status':'FILLED'}
            self.fills.append(fill)
            result.append(fill)
        new_pairs=max(0.,p.paired_qty-before_pairs)
        pair_unit=p.average_up_cost+p.average_down_cost
        self.pairs_created+=new_pairs
        self.pair_cost_sum+=new_pairs*pair_unit
        if pair_unit<1:
            self.pairs_below_one+=new_pairs
        order['fill_qty']=sum(f['fill_qty'] for f in result)
        order['status']='FILLED' if order['fill_qty']>=decision.requested_qty-1e-9 else 'PARTIAL' if result else 'NO_FILL'
        assert self.cash>=-1e-8 and p.up_qty>=0 and p.down_qty>=0 and self.reserved_cash==0
        if abs(self.cash)<1e-10: self.cash=0.
        return result

    def settle(self, identity, winner):
        if winner not in ('UP','DOWN'):
            raise ValueError('A recorded outcome is required for directional settlement')
        if identity.key in self.identities and self.identities[identity.key]!=identity:
            raise ValueError('CROSS_MARKET_REJECT')
        p=self.positions.setdefault(identity.key,Inventory())
        payout=p.up_qty if winner=='UP' else p.down_qty
        self.cash+=payout
        p.realized_pnl+=payout-p.up_cost-p.down_cost
        p.up_qty=p.down_qty=p.up_cost=p.down_cost=0.
        p.expired=True

    def equity_lower_bound(self):
        return self.cash+sum(p.paired_qty for p in self.positions.values())


class Replay:
    def __init__(self,strategy=None,decision_sink=None,**config):
        self.executor=PaperExecutor(**config)
        self.strategy=strategy or NoTrade()
        self.btc=BTCFeatures()
        self.decisions=[]
        self.decision_sink=decision_sink
        self.peak=self.executor.initial_capital
        self.maxdd=self.maxddpct=self.max_directional=self.time_unhedged=0.
        self.last_time=None
        self.last_id=0

    def process(self,event):
        eid,now=event['event_id'],event['available_ts_ms']
        if eid<=self.last_id or (self.last_time is not None and now<self.last_time):
            raise ValueError('Replay must follow recorded availability order')
        directional=sum(abs(p.up_qty-p.down_qty) for p in self.executor.positions.values())
        if self.last_time is not None and directional>1e-9:
            self.time_unhedged+=now-self.last_time
        self.last_time,self.last_id=now,eid
        payload=event['payload']
        kind=event['kind']
        identity=MarketIdentity(**event['identity']) if event.get('identity') else None
        # Expiration blocks trading, but never implies resolution or cash release.
        for key,p in self.executor.positions.items():
            if now>=self.executor.identities[key].expiry_ts_ms:
                p.expired=True
        if kind=='BTC':
            self.btc.update(now,payload)
        elif kind=='BOOK':
            self.executor.update_book(identity,payload)
        elif kind=='RESOLUTION':
            if not payload.get('source') or payload.get('condition_id')!=identity.condition_id:
                raise ValueError('Unverified resolution')
            self.executor.settle(identity,payload['winner'])
        context={'event_id':eid,'now_ms':now,'kind':kind,'identity':identity.fields() if identity else None,
                 'btc':self.btc.at(now),'book':json.loads(encode(payload)) if kind=='BOOK' else None,
                 'inventory':self.executor.positions[identity.key].state() if identity and identity.key in self.executor.positions else None,
                 'cash':self.executor.cash,'reserved_cash':self.executor.reserved_cash}
        decision=self.strategy.on_event(context)
        fills=[]
        if decision.action not in ('NO_TRADE','WAIT'):
            if kind!='BOOK':
                raise ValueError('This initial replay accepts orders only on a current market book event')
            fills=self.executor.execute(identity,decision,now,eid)
        eq=self.executor.equity_lower_bound()
        self.peak=max(self.peak,eq)
        self.maxdd=max(self.maxdd,self.peak-eq)
        self.maxddpct=max(self.maxddpct,(self.peak-eq)/self.peak*100)
        self.max_directional=max(self.max_directional,sum(abs(p.up_qty-p.down_qty) for p in self.executor.positions.values()))
        record={'event_id':eid,'timestamp_ms':now,'decision':asdict(decision),
                               'fill_count':len(fills),'cash':self.executor.cash,'equity_lower_bound':eq,
                               'market_slug':identity.market_slug if identity else None}
        if self.decision_sink:
            self.decision_sink(record)
        else:
            self.decisions.append(record)

    def results(self):
        e=self.executor
        unresolved=any(abs(p.up_qty-p.down_qty)>1e-9 for p in e.positions.values())
        eq=e.equity_lower_bound()
        per_market=[{'market_slug':key[1],**p.state(),
                     'pnl':None if abs(p.up_qty-p.down_qty)>1e-9 else p.realized_pnl+p.paired_qty-p.up_cost-p.down_cost,
                     'pnl_lower_bound':p.realized_pnl+p.paired_qty-p.up_cost-p.down_cost}
                    for key,p in sorted(e.positions.items())]
        known=[m for m in per_market if m['pnl'] is not None]
        gains=sum(max(0.,m['pnl']) for m in known)
        metrics={'initial_capital':e.initial_capital,'final_cash':e.cash,'reserved_cash':e.reserved_cash,
                 'final_capital':None if unresolved else eq,'equity':None if unresolved else eq,
                 'equity_lower_bound':eq,'PnL':None if unresolved else eq-e.initial_capital,
                 'return_pct':None if unresolved else (eq/e.initial_capital-1)*100,
                 'realized_pnl':sum(p.realized_pnl for p in e.positions.values()),
                 'unrealized_pnl':None if unresolved else eq-e.cash-sum(p.up_cost+p.down_cost for p in e.positions.values()),
                 'max_drawdown':self.maxdd,'max_drawdown_pct':self.maxddpct,
                 'number_of_orders':len(e.orders),'number_of_fills':len(e.fills),
                 'fill_rate':sum(o['fill_qty']>0 for o in e.orders)/len(e.orders) if e.orders else None,
                 'up_bought':e.up_bought,'down_bought':e.down_bought,
                 'paired_qty':sum(p.paired_qty for p in e.positions.values()),
                 'directional_up':sum(p.directional_up for p in e.positions.values()),
                 'directional_down':sum(p.directional_down for p in e.positions.values()),
                 'average_pair_cost':e.pair_cost_sum/e.pairs_created if e.pairs_created else None,
                 'percentage_pair_cost_below_1':100*e.pairs_below_one/e.pairs_created if e.pairs_created else None,
                 'fees':e.fees,'slippage':e.slippage_paid,'inventory_turnover':e.turnover/e.initial_capital,
                 'max_directional_exposure':self.max_directional,'time_unhedged_ms':self.time_unhedged,
                 'best_market':max(known,key=lambda m:m['pnl'])['market_slug'] if known else None,
                 'worst_market':min(known,key=lambda m:m['pnl'])['market_slug'] if known else None,
                 'profit_concentration':max((m['pnl'] for m in known),default=0)/gains if gains else None,
                 'status':'UNRESOLVED_DIRECTIONAL_EXPOSURE' if unresolved else 'KNOWN_ECONOMIC_VALUE',
                 'valuation':'cash + guaranteed pairs; directional residual unknown, lower bound zero'}
        assert abs(eq-e.initial_capital-sum(m['pnl_lower_bound'] for m in per_market))<1e-6
        return {'metrics':metrics,'markets':per_market,'decisions':self.decisions,'orders':e.orders,'fills':e.fills}


def replay_database(path, session_id, strategy=None, decision_sink=None, **config):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('BEGIN')
    if [r[0] for r in db.execute('SELECT version FROM schema_info')] not in ([1],[2]):
        raise ValueError('Only D5 schema 1 or 2 may be replayed')
    session=db.execute('SELECT * FROM sessions WHERE session_id=?',(session_id,)).fetchone()
    if not session:
        raise ValueError('Explicit existing D5 session required')
    identities={(r['condition_id'],r['market_slug']):MarketIdentity(r['market_duration'],r['market_slug'],r['condition_id'],
                r['token_up'],r['token_down'],r['expiry_ts_ms']) for r in db.execute('SELECT * FROM markets')}
    replay=Replay(strategy,decision_sink=decision_sink,**config)
    for row in db.execute('SELECT * FROM events WHERE session_id=? ORDER BY event_id',(session_id,)):
        identity=identities.get((row['condition_id'],row['market_slug']))
        replay.process({'event_id':row['event_id'],'kind':row['kind'],'available_ts_ms':row['available_ts_ms'],
                        'payload':decode(row['payload_json']),'identity':identity.fields() if identity else None})
    db.close()
    result=replay.results()
    result['provenance']={'session_id':session_id,'schema_version':session['schema_version'],'config':config,
                          'strategy':type(replay.strategy).__name__,'last_event_id':replay.last_id}
    return result


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--session',required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--demo',action='store_true',help='Synthetic plumbing strategy; not research')
    parser.add_argument('--capital',type=float,default=500.)
    parser.add_argument('--fee-rate',type=float,default=0.)
    parser.add_argument('--friction-per-share',type=float,default=0.)
    parser.add_argument('--slippage',type=float,default=0.)
    args=parser.parse_args()
    if args.out.resolve()==args.db.resolve() or args.out.exists():
        parser.error('Output must be a new file, different from the input database')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.with_suffix('.decisions.jsonl').open('x',encoding='utf-8') as decisions:
        result=replay_database(args.db,args.session,DemoAlternating() if args.demo else NoTrade(),
                               capital=args.capital,fee_rate=args.fee_rate,friction_per_share=args.friction_per_share,
                               slippage=args.slippage,decision_sink=lambda record: decisions.write(encode(record)+'\n'))
    args.out.write_text(encode(result),encoding='utf-8')
    print(encode(result['metrics']))


if __name__=='__main__':
    cli()
