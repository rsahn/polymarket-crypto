"""Summarize D6 timing evidence without payloads or endpoint credentials.

Usage: python analysis/latency_diagnostic_20260925/summarize_latency.py REPORT.json
Overlap proves observed loop occupancy, not GIL or network causation.
"""
import json
import sys
from pathlib import Path


def summarize(report):
    events=report.get('latency_diagnostics',{}).get('events',[])
    sync=[e for e in events if e.get('kind')=='sync' and e['label'].startswith('ws.')]
    def occupancy(start,end):
        spans=sorted((max(start,e['start_ns']),min(end,e['end_ns'])) for e in sync
                     if e['start_ns']<end and e['end_ns']>start)
        total=0;last=start
        for lo,hi in spans:
            total+=max(0,hi-max(last,lo));last=max(last,hi)
        return dict(ws_overlap_wall_ms=total/1e6,
            ws_fully_contained_cpu_ms=sum(e['thread_cpu_ms'] for e in sync
                if start<=e['start_ns'] and e['end_ns']<=end))
    workers=[]
    for e in events:
        if e.get('kind')!='worker' or 'resume_ms' not in e:continue
        workers.append({k:e[k] for k in ('label','queue_ms','worker_ms','resume_ms','thread_cpu_ms')}
                       | occupancy(e['worker_end_ns'],e['resume_ns']))
    phases=[]
    for e in events:
        if e.get('kind')=='await':
            phases.append(dict(label=e['label'],wall_ms=e['wall_ms'],**occupancy(e['start_ns'],e['end_ns'])))
    marks={e['label']:e['at_ns'] for e in events if e.get('kind')=='instant'}
    continuation=None
    if all(k in marks for k in ('generation.result_ready','generation.runner_continued')):
        a,b=(marks[k] for k in ('generation.result_ready','generation.runner_continued'))
        continuation=dict(wall_ms=(b-a)/1e6,**occupancy(a,b))
    scheduler=report.get('scheduler_timing',{})
    historical={}
    for name,entries in [('account',report.get('get_requests',[])),('recheck',report.get('rpc_calls',[]))]:
        start=scheduler.get(name+'_started_ms');end=scheduler.get(name+'_finished_ms')
        if start is None or end is None:continue
        rows=[e for e in entries if start<=e.get('started_ms',-1)<=e.get('finished_ms',-1)<=end]
        if rows:
            historical[name]=dict(phase_ms=end-start,
                last_logged_worker_finish_to_phase_end_ms=end-max(e['finished_ms'] for e in rows),
                longest_logged_request_ms=max(e['finished_ms']-e['started_ms'] for e in rows),
                attribution='UNATTRIBUTED_WITHOUT_OVERLAPPING_TRACE')
    return dict(historical_phase_envelopes=historical,workers=workers,phases=phases,
        generation_continuation=continuation,
        max_loop_lag_ms=max((e['lag_ms'] for e in events if e.get('kind')=='loop_lag'),default=None),
        dropped_events=report.get('latency_diagnostics',{}).get('dropped_events'),
        scope='CPU_OVERLAP_IS_MEASURED_ONLY_FOR_FULLY_CONTAINED_SPANS; NO_GIL_OR_NETWORK_ARRIVAL_CLAIM')


if __name__=='__main__':
    print(json.dumps(summarize(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))),indent=2))
