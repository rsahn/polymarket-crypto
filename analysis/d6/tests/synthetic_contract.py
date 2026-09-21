"""In-memory specification fixtures. No database/network/production imports."""
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Key:
    session: str
    condition: str
    slug: str
    duration: str
    generation: int
    up_token: str
    down_token: str

@dataclass(frozen=True)
class Times:
    source: int | None
    receive: int
    available: int

@dataclass(frozen=True)
class Book:
    key: Key
    event_id: int
    envelope: Times
    up: Times
    down: Times
    generation_start: int
    expiry: int
    clean: bool = True
    value: int = 1

def admissible_times(t, bound, max_age):
    values=(t.source,t.receive,t.available)
    return all(v is not None and 0 <= bound-v <= max_age and v < bound for v in values)

def asof(books, key, token, bound, max_age=1000):
    if token not in (key.up_token,key.down_token):
        return None
    candidates=[b for b in books if b.key==key and b.clean
        and b.generation_start <= b.envelope.available
        and b.generation_start < bound < b.expiry
        and all(admissible_times(t,bound,max_age) for t in (b.envelope,b.up,b.down))]
    if not candidates:
        return None
    ids=[(b.key.session,b.event_id) for b in candidates]
    if len(ids)!=len(set(ids)):
        raise ValueError('duplicate event identity is ambiguous')
    return max(candidates,key=lambda b:(b.envelope.available,b.event_id))

def lag_value(books,key,token,bound,lag,max_age=1000):
    b=asof(books,key,token,bound-lag,max_age)
    return None if b is None else b.value

def prior_buys(operations, condition, action_second, opening=None):
    # Deliberately supports BUY-only fixtures, never pretends to handle unknown burns.
    if opening is None:
        return None
    qty=dict(opening)
    for op in sorted(operations,key=lambda x:x['second']):
        if op['condition']!=condition or op['second']>=action_second:
            continue
        if op['type']!='BUY' or op['side'] not in ('UP','DOWN'):
            return None
        qty[op['side']]+=op['qty']
    return qty

ALLOWED_FEATURES=frozenset({'up_best_bid','up_best_ask','down_best_bid',
    'down_best_ask','btc_return_1s','inventory_imbalance','market_age_ms'})
def project_features(row):
    # An explicit whitelist is essential: unknown names cannot leak a new target.
    if not set(row)<=ALLOWED_FEATURES:
        raise ValueError('not in feature contract')
    return dict(row)

@dataclass(frozen=True)
class Gate:
    writer_closed: bool=False
    manifest_verified: bool=False
    quality_accepted: bool=False
    research_authorized: bool=False
    replay1: str=''
    replay2: str=''

def require_gate(gate):
    if not (gate.writer_closed and gate.manifest_verified and gate.quality_accepted
            and gate.research_authorized and gate.replay1
            and gate.replay1==gate.replay2):
        raise PermissionError('research blocked')

@dataclass(frozen=True)
class MarketInterval:
    slug: str
    condition: str
    feature_start: int
    label_end: int

def split_markets(markets, windows, embargo):
    if embargo<0:
        raise ValueError('negative embargo')
    ranges=sorted(windows.values())
    if any(a>=b for a,b in ranges) or any(b>c for (a,b),(c,d) in zip(ranges,ranges[1:])):
        raise ValueError('overlapping/invalid windows')
    result={};conditions=set()
    for m in markets:
        if m.slug in result or m.condition in conditions:
            raise ValueError('slug or condition shared')
        if m.feature_start>m.label_end:
            raise ValueError('invalid interval')
        conditions.add(m.condition)
        slots=[name for name,(a,b) in windows.items()
               if a+embargo <= m.feature_start <= m.label_end < b-embargo]
        result[m.slug]=slots[0] if len(slots)==1 else 'PURGED'
    return result

class OOSOnce:
    """Toy lifecycle only; production must persist this atomically."""
    def __init__(self):
        self.frozen=None;self.opened=False
    def freeze(self,digest):
        if self.opened or not digest:
            raise ValueError('cannot freeze after OOS or without manifest')
        self.frozen=digest
    def open(self,digest):
        if not self.frozen or digest!=self.frozen or self.opened:
            raise PermissionError('OOS access blocked')
        self.opened=True


def microprice(bid,ask,bid_qty,ask_qty):
    if bid>ask or min(bid_qty,ask_qty)<0 or bid_qty+ask_qty<=0:
        return None
    return (ask*bid_qty+bid*ask_qty)/(bid_qty+ask_qty)

class DepthBudget:
    """Single immutable synthetic liquidity episode, not a replay engine."""
    def __init__(self, asks):
        self.levels=[[Decimal(str(p)),Decimal(str(q))] for p,q in sorted(asks)]
    def buy(self, quantity, cash, fee_rate=Decimal('0')):
        quantity=Decimal(str(quantity));cash=Decimal(str(cash))
        if quantity<0 or cash<0 or fee_rate<0:
            raise ValueError('negative request')
        spent=Decimal('0');filled=Decimal('0')
        for level in self.levels:
            price,qty=level
            unit=price*(1+fee_rate)
            if unit<=0:
                raise ValueError('invalid price')
            take=min(qty,quantity-filled,(cash-spent)/unit)
            level[1]-=take;filled+=take;spent+=take*unit
            if filled==quantity or spent==cash:
                break
        return filled,cash-spent,spent
