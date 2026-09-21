"""Prospective D5.1 criteria. Does not override the historical D5 gate."""
from __future__ import annotations

CONTRACT = 'D5.1'
GAP_LIMIT_MS = 5000
BOUNDARY_LIMIT_MS = 10000
NTP_OFFSET_LIMIT_MS = 100
NTP_DISPERSION_LIMIT_MS = 50
NTP_SYNC_MAX_AGE_SECONDS = 3600


def classify_gap(previous, current, *, reconnect=False, start=False, stop=False):
    """Classification never erases elapsed time or proves message loss."""
    if start:
        return 'STARTUP_GAP'
    if stop:
        return 'SHUTDOWN_GAP'
    if previous is None or current is None:
        raise ValueError('Interior gap requires two observations')
    if previous['slug'] != current['slug']:
        return 'TRANSITION_GAP'
    if reconnect or previous.get('generation') != current.get('generation'):
        return 'RECONNECT_GAP'
    return 'INTERNAL_FEED_GAP'


def gap_failure(kind, elapsed_ms, *, transition_verified=False):
    if elapsed_ms < 0:
        return 'RECEIVE_CLOCK_REGRESSION'
    if kind in ('STARTUP_GAP','SHUTDOWN_GAP'):
        return 'BOUNDARY_GAP_OVER_10S' if elapsed_ms > BOUNDARY_LIMIT_MS else None
    if kind == 'TRANSITION_GAP':
        # A bounded expected expiry transition is not an internal feed loss.
        # No blanket exemption for a different slug.
        if not transition_verified:
            return 'UNVERIFIED_TRANSITION'
        return 'TRANSITION_GAP_OVER_10S' if elapsed_ms > BOUNDARY_LIMIT_MS else None
    if kind not in ('INTERNAL_FEED_GAP','RECONNECT_GAP'):
        raise ValueError('Unknown gap type')
    return kind+'_OVER_5S' if elapsed_ms > GAP_LIMIT_MS else None


def ntp_gate(snapshot):
    import math
    failures=[]
    refs=snapshot.get('references',{})
    for name in ('time.windows.com','time.cloudflare.com'):
        r=refs.get(name,{})
        samples=r.get('samples',[])
        if len(samples)<3 or not r.get('valid',False):
            failures.append('NTP_EVIDENCE_MISSING_'+name); continue
        if any(not all(isinstance(x.get(k),(int,float)) and math.isfinite(x[k]) for k in ('offset_ms','dispersion_ms','delay_ms')) for x in samples):
            failures.append('NTP_NONFINITE_'+name); continue
        if any(x['delay_ms'] < -1 or x['delay_ms'] > 1000 or x['dispersion_ms'] < 0 for x in samples):
            failures.append('NTP_INVALID_BOUNDS_'+name)
        if any(abs(x['offset_ms'])>NTP_OFFSET_LIMIT_MS for x in samples):
            failures.append('NTP_OFFSET_'+name)
        if any(x['dispersion_ms']>NTP_DISPERSION_LIMIT_MS for x in samples):
            failures.append('NTP_DISPERSION_'+name)
    w=snapshot.get('w32time',{})
    if w.get('service')!='Running': failures.append('W32TIME_NOT_RUNNING')
    if w.get('last_sync_error')!=0: failures.append('W32TIME_SYNC_ERROR')
    age=w.get('last_sync_age_seconds')
    if age is None or age<0 or age>NTP_SYNC_MAX_AGE_SECONDS: failures.append('W32TIME_STALE_SYNC')
    if not w.get('source'): failures.append('W32TIME_SOURCE_MISSING')
    return sorted(set(failures))
