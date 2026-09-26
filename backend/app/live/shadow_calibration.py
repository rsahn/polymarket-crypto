"""Bounded, opt-in, read-only metrics. No network, orders, wallets or file I/O.
Hypothetical VWAP excludes fees, queue priority and execution latency. It is NOT
an executable quote or proof of realized slippage. No SLA is fitted here.
"""
from collections import deque, Counter, OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
import hashlib
from .temporal_contract import age_ms

_current=ContextVar('d6_shadow_calibration',default=None)
def current_calibration():return _current.get()

@contextmanager
def calibration_session(recorder):
    token=_current.set(recorder)
    try:yield recorder
    finally:_current.reset(token)


class ShadowCalibration:
    def __init__(self,*,shares,capacity=4096):
        if isinstance(shares,bool):raise ValueError('INVALID_HYPOTHETICAL_SIZE')
        self.shares=Decimal(str(shares))
        if not self.shares.is_finite() or self.shares<=0:raise ValueError('INVALID_HYPOTHETICAL_SIZE')
        if type(capacity) is not int or not 1<=capacity<=65536:raise ValueError('INVALID_CAPACITY')
        self.capacity=capacity;self.books=deque(maxlen=capacity);self.signals=deque(maxlen=capacity);self.generations=deque(maxlen=capacity)
        self.last=OrderedDict();self.dropped=0;self.rejections=Counter();self.errors=0
    def append(self,queue,row):
        if len(queue)==self.capacity:self.dropped+=1
        queue.append(row)
    @staticmethod
    def key(market,generation,token_index):
        return (hashlib.sha256(str(market).encode()).hexdigest(),generation,token_index)
    def book(self,market,generation,token_index,*,source_ms,received_ms,decision_ms,bids,asks,sample_stage="BOOK_PROCESSING_OBSERVATION"):
        if age_ms(source_ms,decision_ms) is None or age_ms(received_ms,decision_ms) is None:raise ValueError('TIMESTAMP_INVALID')
        key=self.key(market,generation,token_index);prev=self.last.get(key)
        bids=sorted(((Decimal(str(p)),Decimal(str(q))) for p,q in bids),reverse=True)
        asks=sorted((Decimal(str(p)),Decimal(str(q))) for p,q in asks)
        if any(not p.is_finite() or not q.is_finite() or not 0<p<1 or q<=0 for p,q in bids+asks):raise ValueError('DEPTH_INVALID')
        if (len({p for p,q in bids})!=len(bids) or len({p for p,q in asks})!=len(asks)
            or bids and asks and bids[0][0]>=asks[0][0]):raise ValueError('DEPTH_INVALID')
        bid=float(bids[0][0]) if bids else None;ask=float(asks[0][0]) if asks else None
        remaining=self.shares;cost=Decimal(0)
        for price,size in asks:
            take=min(size,remaining);cost+=take*price;remaining-=take
            if remaining==0:break
        vwap=cost/self.shares if remaining==0 else None
        row=dict(sample_stage=sample_stage,decision_is_execution=False,market_sha256=key[0],generation=generation,token_index=token_index,
            source_ms=source_ms,received_ms=received_ms,decision_ms=decision_ms,book_age_ms=decision_ms-source_ms,
            receive_age_ms=decision_ms-received_ms,update_interval_ms=received_ms-prev['received_ms'] if prev else None,
            best_bid=bid,best_ask=ask,spread=ask-bid if bid is not None and ask is not None else None,
            bid_depth=float(sum((q for p,q in bids),Decimal(0))),ask_depth=float(sum((q for p,q in asks),Decimal(0))),
            hypothetical_shares=str(self.shares),hypothetical_buy_price=float(vwap) if vwap is not None else None,
            hypothetical_slippage_bps=float((vwap/asks[0][0]-1)*10000) if vwap is not None else None,
            insufficient_depth=remaining!=0)
        for name in ('best_bid','best_ask','spread','bid_depth','ask_depth','hypothetical_buy_price'):
            row[name+'_movement']=row[name]-prev[name] if prev and row[name] is not None and prev[name] is not None else None
        if prev and (source_ms<prev['source_ms'] or received_ms<prev['received_ms']):raise ValueError('TIMESTAMP_REGRESSION')
        self.append(self.books,row);self.last[key]=row;self.last.move_to_end(key)
        while len(self.last)>self.capacity:self.last.popitem(last=False)
    def signal(self,market,generation,token_index,*,source_ms,received_ms,decision_ms):
        # Optional tap for a real V1 decision. Never infer signals from book updates.
        key=self.key(market,generation,token_index);book=self.last.get(key)
        causal=book and book['received_ms']<=decision_ms and book['decision_ms']<=decision_ms
        self.append(self.signals,dict(market_sha256=key[0],generation=generation,token_index=token_index,
            source_ms=source_ms,received_ms=received_ms,decision_ms=decision_ms,
            signal_age_ms=age_ms(source_ms,decision_ms),signal_receive_age_ms=age_ms(received_ms,decision_ms),
            book_age_at_signal_ms=age_ms(book['source_ms'],decision_ms) if causal else None))
    def generation(self,generation,decision_ms,timestamps,*,signal=None):
        names={'book':'book_age_ms','balance':'balance_age_ms','orders':'orders_age_ms',
               'positions':'positions_age_ms','inventory':'inventory_proof_age_ms'}
        row=dict(generation=generation,decision_ms=decision_ms,original_timestamps=dict(timestamps),
            **{field:age_ms(timestamps.get(name),decision_ms) for name,field in names.items()})
        row.update(signal_age_ms=age_ms(signal.get('source_ms'),decision_ms) if signal else None,
                   signal_status='OBSERVED' if signal else 'NOT_OBSERVED')
        self.append(self.generations,row)
    def report(self):
        def distribution(values):
            v=sorted(x for x in values if x is not None)
            return dict(n=len(v),min=v[0] if v else None,median=v[len(v)//2] if v else None,
                        p95=v[min(len(v)-1,int(.95*len(v)))] if v else None,max=v[-1] if v else None)
        return dict(mode='SHADOW_CALIBRATION_READ_ONLY',book_samples=list(self.books),signal_samples=list(self.signals),
            generations=list(self.generations),dropped_samples=self.dropped,capacity=self.capacity,
            rejection_counts=dict(self.rejections),instrumentation_errors=self.errors,
            age_distributions={k:distribution(r.get(k) for r in self.generations) for k in
                ('book_age_ms','signal_age_ms','balance_age_ms','orders_age_ms','positions_age_ms','inventory_proof_age_ms')},
            book_age_distribution=distribution(r['book_age_ms'] for r in self.books),
            selection_bias='ACCEPTED_BOOKS_ONLY_WITH_EXPLICIT_REJECTION_COUNTS',
            limitations=['BOUNDED_SAMPLE_NOT_FULL_DATASET','REJECTED_BOOK_DEPTH_NOT_RECONSTRUCTED',
                'BOOK_PROCESSING_TIMESTAMP_IS_NOT_EXECUTION_DECISION','NO_REALIZED_FILLS_OR_FEES','BTC_V1_NOT_RUN_BY_READINESS_QUALIFIER','NO_SLA_SELECTED'],
            sla_calibrated=False,real_fills=0,submit_allowed=False)
