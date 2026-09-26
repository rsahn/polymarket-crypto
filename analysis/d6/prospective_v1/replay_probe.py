"""Bounded synthetic measurement of the already identified state-copy blocker.
No strategy, real dataset partition, network or production process is opened.
"""
import argparse,copy,json,time
from pathlib import Path
from .core import safety,digest
from .journal import DurableEventJournal
from .engine import ProspectiveEventAdapter
from .storage_smoke import peak_rss

def probe(out, sizes=(100,1000,5000)):
    safety();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    identity=dict(strategy_hash="synthetic",runner_hash="synthetic",
                  dataset_session_id="TECHNICAL_REPLAY_ONLY",partition="TRAIN")
    results=[]
    for size in sizes:
        path=out/f"synthetic_{size}.jsonl"
        j=DurableEventJournal(path,identity);a=ProspectiveEventAdapter(j,{},synthetic=True)
        start=time.perf_counter()
        # Build valid committed observations without O(N^2) preview copies.
        # _apply is used only by this probe; production observe remains unchanged.
        for n in range(size):
            e=dict(event_id=str(n),kind="MARK",market_id="synthetic",token_id="synthetic",
                direction="UP",source_ts=n,recv_ts=n,decision_ts=n,event_ts=n,
                book_ts=None,price=None,qty=None,notional=None,fee=None,net_unit_marks={})
            j.append(e);a._apply(j.records[-1])
        append_seconds=time.perf_counter()-start
        copies=[]
        for _ in range(5):
            start=time.perf_counter()
            detached={k:copy.deepcopy(v) for k,v in a.__dict__.items() if k!="journal"}
            copies.append(time.perf_counter()-start)
            del detached
        e.update(event_id=str(size),source_ts=size,recv_ts=size,decision_ts=size,event_ts=size)
        start=time.perf_counter();a.observe(e);observe_seconds=time.perf_counter()-start
        expected=digest(a.accounting);j.close()
        del a,j
        start=time.perf_counter();recovered=DurableEventJournal(path,identity)
        journal_seconds=time.perf_counter()-start
        start=time.perf_counter();b=ProspectiveEventAdapter(recovered,{},synthetic=True)
        ledger_seconds=time.perf_counter()-start
        if digest(b.accounting)!=expected:raise ValueError("RECOVERY_MISMATCH")
        results.append(dict(events=size+1,bytes=path.stat().st_size,
            bytes_per_event=path.stat().st_size/(size+1),append_fsync_seconds=append_seconds,
            state_copy_samples_seconds=copies,observe_seconds=observe_seconds,
            journal_recovery_seconds=journal_seconds,journal_recovery_events_per_second=(size+1)/journal_seconds,
            adapter_replay_seconds=ledger_seconds,peak_process_rss_bytes=peak_rss(),recovery="PASS"))
        recovered.close();del b,recovered
        print(json.dumps(results[-1]),flush=True)
    result=dict(status="REPLAY_CAPACITY_UNPROVEN",fixture="SYNTHETIC_MARK_ONLY",
        real_partition_opened=False,synthetic_schema_partition_label="TRAIN",
        limitation="Small synthetic MARK history; real books, trades, fee annotations and 168h are not qualified. Journal and accounting retain O(N) records; observe copies accumulated state.",
        journal_allowance=None,checkpoint_allowance=None,results=results,**safety())
    (out/"RESULT.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args();probe(a.out)
