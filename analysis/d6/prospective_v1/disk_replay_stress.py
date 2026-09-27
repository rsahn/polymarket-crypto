"""Offline synthetic scaling probe; no collection, PnL study or real partitions."""
import json,sys,time,socket
from pathlib import Path
from .core import encode,file_hash,safety
from .disk_replay import replay_disk
from .test_closure_delta import chain
from .test_harness import event,IDENTITY,fee


def events(kind,count):
    for i in range(count):
        if kind=='marks': yield event('MARK',n=i+1,net_unit_marks={})
        else:
            phase=i%3;kw={};k=('SIGNAL','ENTRY_INTENT','ENTRY_BOOK')[phase]
            if phase==1:kw['notional']='25'
            if phase==2:kw.update(book_ts=i+1,asks=[['.5','50']],bids=[['.49','50']])
            e=event(k,n=i+1);e.update(kw);e['trade_id']='trade-'+str(i//3);yield e


def run(directory,output):
    from .storage_smoke import peak_rss
    safety();directory=Path(directory);directory.mkdir(exist_ok=False)
    attempts=[]
    def audit(name,args):
        if name=='socket.connect':attempts.append('blocked');raise RuntimeError('OFFLINE_ONLY')
    sys.addaudithook(audit)
    result=[]
    # Fixed sizes before measurement; not selected on economic results.
    for kind,count in [('marks',100000),('book_history',60000)]:
        source=directory/(kind+'.jsonl')
        with source.open('x',encoding='utf-8') as f:
            for row in chain(events(kind,count)):f.write(encode(row)+'\n')
        sha=file_hash(source);samples=[];start=time.perf_counter()
        def sample(n,a,s):
            peak=peak_rss()
            samples.append(dict(events=n,seconds=time.perf_counter()-start,peak_rss=peak,accounting_rows=len(a.accounting),
                trade_states=len(a.states),books=sum(len(v) for v in a.tape.books.values()),
                scratch_bytes=s.path.stat().st_size))
        a,meta,s=replay_disk(source,IDENTITY,{('m','t'):fee()},directory/(kind+'.db'),
                             directory/(kind+'-ids.db'),synthetic=True,progress=sample)
        try:
            elapsed=time.perf_counter()-start
            result.append(dict(kind=kind,events=count,elapsed_seconds=elapsed,events_per_second=count/elapsed,
                samples=samples,final_mark=a.ledger.mark(a.marks),metadata=meta,
                source_sha256=sha,source_unchanged=sha==file_hash(source),
                input_bytes=source.stat().st_size,scratch_bytes=s.path.stat().st_size,
                id_index_bytes=(directory/(kind+'-ids.db')).stat().st_size,
                protocol_wide_memory_bound=False,technical_only=True))
        finally:s.close()
        Path(output).with_name(kind+'_STRESS.json').open('x',encoding='utf-8').write(encode(result[-1])+'\n')
        print(kind,count,round(elapsed,3),flush=True)
    Path(output).open('x',encoding='utf-8').write(encode(dict(runs=result,network_attempts=len(attempts),
        sdk_monetary_attempts=0,sdk_clients_created=0,flags=safety(),week_capacity_qualified=False))+'\n')

if __name__=='__main__':run(sys.argv[1],sys.argv[2])
