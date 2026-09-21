"""Isolated technical benchmark. No network, collection DB, research or trading."""
import datetime,json,multiprocessing as mp,pathlib,queue,sys,time,traceback
ROOT=pathlib.Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from app.d5.identity import MarketIdentity
from app.d5.store import Store,code_version
from app.d5.observer import Observer

def worker(channel,out,identities,start_ms):
    store=None
    try:
        store=Store(out/'technical_only.db',{'technical_diagnostic_only':True},compress_payloads=True);observer=Observer(store)
        for identity in identities.values():observer.activate(identity,1,start_ms)
        expected=0;last_flush=start_ms;last_sequence=-1;began=time.perf_counter()
        while True:
            item=channel.get()
            if item is None:break
            sequence,feed,snapshot,observed_ms=item
            if sequence!=expected:raise AssertionError(('sequence',sequence,expected))
            observer.observe(identities[feed],1,snapshot,{},observed_ms)
            expected+=1;last_sequence=sequence
            if observed_ms-last_flush>=500:store.flush();last_flush=observed_ms
            if expected%10000==0:
                (out/'worker_progress.json').write_text(json.dumps(dict(rows=expected,last_sequence=last_sequence,seconds=time.perf_counter()-began)))
        store.flush();counts=dict(store.counts);store.close('TECHNICAL_DIAGNOSTIC_ONLY');store=None
        (out/'worker_result.json').write_text(json.dumps(dict(status='PASS',rows=expected,last_sequence=last_sequence,counts=counts,seconds=time.perf_counter()-began)))
    except BaseException:
        (out/'worker_failure.txt').write_text(traceback.format_exc())
        if store is not None:store.close('TECHNICAL_FAILED')
        raise

def main():
    source=ROOT/'analysis/d51/raw_probe_20260921_125200'
    out=ROOT/'analysis/d51'/('process_writer_profile_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir(exist_ok=False)
    rows=[];collectors={};identities={}
    for feed in ('5m','15m'):
        market=json.loads((source/(feed+'_identity.json')).read_text())['market'];identity=MarketIdentity.from_market(market);identities[feed]=identity
        collectors[feed]=PolymarketOrderbookCollector(feed,{'UP':identity.token_up,'DOWN':identity.token_down},None,identity.expiry_ts_ms,identity=identity,timestamp_contract='D5.1');collectors[feed]._connection_generation=1
        with (source/(feed+'_raw.jsonl')).open(encoding='utf-8') as f:
            for line in f:
                r=json.loads(line);rows.append((r['monotonic_ns'],feed,r))
    rows.sort(key=lambda x:x[0]);ctx=mp.get_context('spawn');channel=ctx.Queue(maxsize=256)
    process=ctx.Process(target=worker,args=(channel,out,identities,rows[0][2]['received_ms']))
    began=time.perf_counter();process.start();sent=0;wait_seconds=0.;normalize_seconds=0.
    def send(item):
        nonlocal wait_seconds
        start=time.perf_counter()
        while True:
            if process.exitcode is not None:raise RuntimeError('Writer exited before drain: '+str(process.exitcode))
            try:channel.put(item,timeout=.5);break
            except queue.Full:pass
        wait_seconds+=time.perf_counter()-start
    for _,feed,row in rows:
        try:payload=json.loads(row['raw'])
        except (ValueError,TypeError):continue
        if not isinstance(payload,(dict,list)):continue
        t=time.perf_counter();snapshot=collectors[feed].normalize_snapshot(payload,row['received_ms']);normalize_seconds+=time.perf_counter()-t
        send((sent,feed,snapshot,row['received_ms']));sent+=1
    send(None)
    while process.is_alive():process.join(timeout=1)
    channel.close();channel.join_thread()
    if process.exitcode!=0:raise RuntimeError('Writer failed: '+str(process.exitcode))
    result=json.loads((out/'worker_result.json').read_text());assert result['rows']==sent
    elapsed=time.perf_counter()-began
    result.update(technical_only=True,not_D6=True,not_prospective=True,frames=sent,total_seconds=elapsed,frames_per_second=sent/elapsed,normalize_seconds=normalize_seconds,queue_put_wall_seconds=wait_seconds,queue_capacity=256,no_dropped_frames=True,drained=True,code_version=code_version(),timing_note='Captured timestamps reused only in technical fixture; not a live latency measurement. Includes process startup and drain.')
    (out/'result.json').write_text(json.dumps(result,indent=2));print(str(out),flush=True);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
