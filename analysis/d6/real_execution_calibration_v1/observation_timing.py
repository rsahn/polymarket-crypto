"""Read intervals are freshness bounds, NOT atomic or source-state frontiers."""
import copy,time
from .binding_consumer import require

def now_ms():return time.time_ns()//1000000

class TimedTransport:
    def __init__(self,inner,clock=now_ms):self.inner=inner;self.clock=clock;self.pages=[]
    @property
    def observations(self):return getattr(self.inner,'observations',[])
    async def get_json(self,path,params=None,**kw):
        start=self.clock();raw=None;before=len(getattr(self.inner,'audit',[]))
        try:
            raw=await self.inner.get_json(path,params=params,**kw);return raw
        finally:
            end=self.clock();audit=getattr(self.inner,'audit',[])
            receive=audit[-1].get('response_received_ms',end) if len(audit)>before else end
            source={k:raw[k] for k in ('observed_ms','source_observed_ms') if type(raw) is dict and k in raw}
            self.pages.append(dict(path=path,read_start_ms=start,receive_ms=receive,read_end_ms=end,producer_timestamps=source,receive_basis='TRANSPORT_READ_COMPLETE' if len(audit)>before else 'RETURN_TIME_UPPER_BOUND'))

def finish_observation(value,start,end,pages,expiry_ms=None):
    v=copy.deepcopy(value);anchors=[start];reason=None
    try:
        require(type(start) is int and type(end) is int and 0<=start<=end,'READ_CLOCK_REGRESSION')
        # Preserve producer fields verbatim. Consumers use freshness_anchor_ms.
        for key in ('observed_ms','source_observed_ms'):
            if key in v:
                t=v[key];require(type(t) is int and 0<=t<=end,'PRODUCER_TIMESTAMP_INVALID');anchors.append(t)
        for p in pages:
            a,c,z=p['read_start_ms'],p['receive_ms'],p['read_end_ms']
            require(all(type(t) is int for t in (a,c,z)) and start<=a<=c<=z<=end,'PAGE_TIMING_INVALID');anchors.append(a)
            for t in p['producer_timestamps'].values():
                require(type(t) is int and 0<=t<=c,'PAGE_SOURCE_TIMESTAMP_INVALID');anchors.append(t)
        if end-min(anchors)>5000:reason='OLDEST_OBSERVATION_STALE'
        if expiry_ms is not None and (type(expiry_ms) is not int or end>=expiry_ms):reason='MARKET_EXPIRED_DURING_OBSERVATION'
    except ValueError as exc:reason=str(exc)
    anchor=min(anchors)
    v.update(timing_schema='READ_INTERVALS_OLDEST_ANCHOR/1',read_interval_ms={'start':start,'end':end},page_timestamps=copy.deepcopy(pages),freshness_anchor_ms=anchor,valid_until_ms=anchor+5000)
    v.setdefault('observed_ms',anchor)
    if reason:
        if v.get('status')=='UNAVAILABLE' and v.get('reason'):v['operation_reason']=v['reason']
        v.update(status='UNAVAILABLE',reason=reason,rows=None,count=None)
    return v

async def timed_stage(op,transports,*,clock=now_ms,expiry_ms=None):
    start=clock();offsets=[len(t.pages) for t in transports]
    from .compare_accounts import safe_reason
    import asyncio
    try:value=await asyncio.wait_for(op(),25)
    except Exception as exc:value=dict(status='UNAVAILABLE',reason=safe_reason(exc),rows=None,count=None)
    pages=[p for t,n in zip(transports,offsets) for p in t.pages[n:]]
    return finish_observation(value,start,clock(),pages,expiry_ms)
