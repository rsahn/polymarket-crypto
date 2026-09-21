"""Post-review read-only latency census. Descriptive thresholds, never a quality override."""
import argparse,collections,datetime,hashlib,json,math,pathlib,sqlite3,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'analysis/d5/auditor_next')]
from app.d5.store import decode
from atomic_status import write_status

class Histogram:
    def __init__(self):self.counts=collections.Counter();self.missing=0;self.invalid=0
    def add(self,value):
        if value is None:self.missing+=1
        elif type(value) is not int:self.invalid+=1
        else:self.counts[value]+=1
    def report(self):
        n=sum(self.counts.values());quantiles={};running=0
        for value,count in sorted(self.counts.items()):
            running+=count
            for label,q in [('p50',.5),('p95',.95),('p99',.99)]:
                if label not in quantiles and running>=math.ceil(q*n):quantiles[label]=value
        return dict(n=n,missing=self.missing,invalid=self.invalid,min_ms=min(self.counts,default=None),max_ms=max(self.counts,default=None),mean_ms=sum(v*c for v,c in self.counts.items())/n if n else None,quantiles_ms=quantiles,negative_count=sum(c for v,c in self.counts.items() if v<0),over_ms={str(t):{'count':sum(c for v,c in self.counts.items() if v>t),'fraction':sum(c for v,c in self.counts.items() if v>t)/n if n else None} for t in (1000,5000,10000,30000)},histogram_ms=sorted(self.counts.items()))

def run(directory):
    directory=pathlib.Path(directory).resolve();allowed=(ROOT/'analysis/d51').resolve()
    if not directory.is_relative_to(allowed):raise ValueError('D5.1 run directory required')
    state=json.loads((directory/'status.json').read_text());review=json.loads((directory/'review/progress.json').read_text());final=json.loads((directory/'review/D51_FINAL_REPORT.json').read_text())
    if state['phase']!='COMPLETE' or state.get('keep_awake') is not False or review['status']!='COMPLETE':raise RuntimeError('Review must be fully closed before this diagnostic')
    source=pathlib.Path(state['database']).resolve()
    if not source.is_relative_to((ROOT/'data/d51').resolve()):raise ValueError('Unexpected source directory')
    out=directory/'post_review_latency';out.mkdir(exist_ok=False)
    before=(source.stat().st_size,source.stat().st_mtime_ns);begin=time.monotonic();total=final['report']['TOTAL_EVENTS'];rows=0;groups={};types=collections.Counter();worst={}
    def progress(phase):write_status(out/'progress.json',dict(phase=phase,rows=rows,total=total,elapsed_seconds=time.monotonic()-begin,rows_per_second=rows/max(time.monotonic()-begin,.001),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    progress('RUNNING')
    try:
        db=sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON')
        try:
            for eid,kind,feed,source_ms,received,available,payload in db.execute('SELECT event_id,kind,market_duration,event_ts_ms,received_ts_ms,available_ts_ms,payload_json FROM events ORDER BY event_id'):
                rows+=1
                if kind in ('BOOK','BTC'):
                    feed=feed if kind=='BOOK' else 'BTC'
                    hist=groups.setdefault(feed,{n:Histogram() for n in ('wire_age','state_age','processing')})
                    raw=decode(payload) if kind=='BOOK' else None
                    wire=raw.get('wire_event_ts_ms') if raw else source_ms
                    wire_age=received-wire if type(wire) is int else None
                    hist['wire_age'].add(wire_age);hist['state_age'].add(received-source_ms if type(source_ms) is int else None);hist['processing'].add(available-received)
                    if raw:
                        for m in raw.get('source_metadata',[]):types[(feed,str(m.get('event_type',m.get('type'))))]+=1
                    if wire_age is not None and (feed not in worst or wire_age>worst[feed]['wire_age_ms']):worst[feed]=dict(event_id=eid,wire_age_ms=wire_age,wire_ms=wire,source_ms=source_ms,received_ms=received,available_ms=available)
                if rows%10000==0:progress('RUNNING')
        finally:db.close()
        if rows!=total:raise RuntimeError('Row count mismatch')
        stable=before==(source.stat().st_size,source.stat().st_mtime_ns)
        if not stable:raise RuntimeError('Source stat changed')
        result=dict(diagnostic_only=True,quality_verdict_unchanged=final['D51_DATA_QUALITY'],thresholds_are_descriptive_not_gate_changes=True,source=str(source),source_sha256_from_completed_review_not_rehashed=final['source_sha256'],source_stat_unchanged=stable,rows=rows,feeds={f:{k:h.report() for k,h in hs.items()} for f,hs in groups.items()},worst_wire_events=worst,wire_types=[dict(feed=f,event_type=t,count=n) for (f,t),n in sorted(types.items())],seconds=time.monotonic()-begin,script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
        with (out/'LATENCY_DIAGNOSIS.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
        progress('COMPLETE')
    except BaseException as exc:progress('FAILED');raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=pathlib.Path);a=p.parse_args();run(a.run)
