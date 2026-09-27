"""Offline historical depth audit. Never infer actual entry clocks from sleeps."""
import json, sqlite3, zlib
from pathlib import Path
from .core import digest

def unpack(value):
    return json.loads(zlib.decompress(value) if isinstance(value,bytes) else value)

def relation(previous,current):
    if not previous or not current or previous.get("token")!=current.get("token"):
        return "C"
    keys=("source_ts","receive_ts","source_hash","sequence","generation")
    if any(previous.get(k) is None or current.get(k) is None for k in ("source_ts","receive_ts","generation")):
        return "C"
    if any(previous.get(k)!=current.get(k) for k in keys):
        return "B"
    # Matching state metadata does not prove that all intervening messages exist.
    return "C"

def summarize(rows):
    proven=[r for r in rows if r.get("book_identity") is not None and r.get("entry_decision_ts") is not None]
    reused=[r for r in proven if r.get("same_book_as_previous") is True]
    return dict(opportunities_examined=len(rows),identified_entry_books=len(proven),
        same_book_reuse_count=len(reused) if len(proven)==len(rows) else None,
        same_book_reuse_rate=len(reused)/len(rows) if rows and len(proven)==len(rows) else None,
        same_book_same_token_count=None,overlapping_lifetime_count=None,
        new_update_between_opportunities_count=None,unknown_cases=len(rows)-len(proven),
        classification="DEPTH_MODEL_NOT_IDENTIFIABLE_FROM_CURRENT_EVIDENCE")

def audit(root):
    root=Path(root); reports=sorted((root/'analysis/d6/paper_live').glob('paper_*.json'))
    signals={};fills={};sources={}
    for p in reports:
        d=json.loads(p.read_text());sources[str(p.relative_to(root))]=digest(d)
        for s in d.get('signals',[]): signals[s['ts_ms'],s['side']]=s
        for f in d.get('fills',[]):
            if f.get('portfolio')=='fixed_25' or f.get('status')=='SKIP':
                fills[f['signal_ts_ms'],f['side']]=f
    dbs=[]
    for p in sorted((root/'data/d6').glob('*.db')):
        # Never ignore a nonempty WAL: its uncheckpointed view is not this audit's evidence.
        wal=Path(str(p)+'-wal')
        if wal.exists() and wal.stat().st_size: continue
        c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        sessions=c.execute('select session_id,started_at_ms,ended_at_ms from sessions').fetchall()
        dbs.append((p,c,sessions,p.stat().st_size,p.stat().st_mtime_ns))
    rows=[];prior=None
    try:
        for (ts,side),s in sorted(signals.items()):
            f=fills.get((ts,side),{});slug=f.get('slug')
            r=dict(opportunity_id=str(ts)+':'+side,signal_ts=ts,side=side,entry_decision_ts=None,
                token=None,book_identity=None,book_source_ts=None,book_receive_ts=None,
                last_book_update_before_entry=None,next_book_update_after_entry=None,depth_used=None,
                previous_opportunity_book_identity=None,same_book_as_previous=None,
                elapsed_since_previous_opportunity_ms=ts-prior if prior is not None else None,
                case='C',reason='Actual entry clock/book/levels absent from historical callback',
                historical_fill=f or None,nominal_target_ms=ts+250,nominal_diagnostics=[])
            prior=ts
            for p,c,sessions,_,_ in dbs:
                if not any(start<=ts and (end is None or ts<=end) for _,start,end in sessions):continue
                candidates=[]
                if slug:
                    token=c.execute('select token_up,token_down from markets where market_slug=?',(slug,)).fetchone()
                    if token:r['token']=token[0 if side=='UP' else 1]
                    q="""select e.event_id,e.event_ts_ms,e.received_ts_ms,e.available_ts_ms,e.generation,
                    b.event_ts_ms,b.received_ts_ms,b.source_hash,b.sequence,b.bids_json,b.asks_json,e.payload_json
                    from events e join book_sides b on e.event_id=b.event_id
                    where e.market_slug=? and e.kind='BOOK' and b.side=? and e.received_ts_ms between ? and ?
                    order by e.event_id"""
                    for row in c.execute(q,(slug,side,ts-500,ts+2500)):
                        eid,ets,ert,av,gen,st,rt,sh,seq,bids,asks,payload=row
                        payload=unpack(payload)
                        candidates.append(dict(event_id=eid,local_sequence=eid,source_ts=st,receive_ts=rt,
                            envelope_receive_ts=ert,persistence_available_ts=av,generation=gen,source_hash=sh,
                            sequence=seq,token=r['token'],wire_hash=payload.get('wire_hash'),
                            connection_generation=payload.get('connection_generation'),
                            source_metadata=payload.get('source_metadata'),bids=unpack(bids),asks=unpack(asks)))
                    before=[x for x in candidates if x['envelope_receive_ts']<=ts+250]
                    after=[x for x in candidates if x['envelope_receive_ts']>ts+250]
                    chosen=([before[-1]] if before else [])+([after[0]] if after else [])
                    r['nominal_diagnostics'].append(dict(database=str(p.relative_to(root)),candidate_count=len(candidates),
                        brackets=chosen,bracket_relation=relation(*chosen) if len(chosen)==2 else 'C',
                        actual_entry_binding=False))
            rows.append(r)
        checks=[dict(path=str(p.relative_to(root)),size=size,mtime_ns=mt,
            unchanged=(p.stat().st_size==size and p.stat().st_mtime_ns==mt)) for p,c,se,size,mt in dbs]
        assert all(x['unchanged'] for x in checks)
    finally:
        for _,c,*_ in dbs:c.close()
    return dict(summary=summarize(rows),opportunities=rows,report_hashes=sources,source_checks=checks,
        compact_windows='No existing compact/window DB located under analysis or data; extractor is code only.',
        excluded='Loose soak WAL/SHM without base DB not a recoverable causal capture; no repair attempted.',
        impact=dict(opportunities_affected=None,fills_affected=None,quantity_difference=None,pnl_difference=None,
                    unresolved=len(rows),model_C='Not admissibly demonstrated, not evaluated'))


def technical_observations(path,limit=1000):
    """Prespecified prefix diagnostic; never treated as economic opportunities."""
    from collections import Counter
    path=Path(path);before=(path.stat().st_size,path.stat().st_mtime_ns)
    c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    prior={};counts=Counter();examples={};previous_eid=None
    try:
        for eid,gen,payload in c.execute("select event_id,generation,payload_json from events where kind='BOOK' and market_duration='5m' order by event_id limit ?",(limit,)):
            p=unpack(payload);counts['book_envelopes']+=1
            kinds=tuple(x.get('event_type',x.get('type','UNKNOWN')) for x in p.get('source_metadata',[]))
            counts['wire_types:'+','.join(str(x) for x in kinds)]+=1
            for side in ('up','down'):
                q=p[side];token=q['token_id']
                state=dict(token=token,source_ts=q.get('event_ts_ms'),receive_ts=q.get('received_ts_ms'),
                    source_hash=q.get('source_hash'),sequence=q.get('sequence'),generation=gen)
                state['depth_hash']=digest([q.get('bids'),q.get('asks')]);old=prior.get(token)
                unchanged=old==state if old else None
                counts['token_observations']+=1
                if q.get('sequence') is None:counts['sequence_missing']+=1
                if old:
                    counts['unchanged_token_state_reemitted' if unchanged else 'changed_token_state']+=1
                    if old['depth_hash']==state['depth_hash']:counts['same_depth_values']+=1
                label=','.join(str(x) for x in kinds)+':'+str(unchanged)
                if label not in examples:examples[label]=dict(event_id=eid,previous_envelope_event_id=previous_eid,
                    state=state,previous_token_state=old,wire_hash=p.get('wire_hash'),
                    wire_event_ts_ms=p.get('wire_event_ts_ms'),envelope_receive_ts=p.get('received_ts_ms'),
                    connection_generation=p.get('connection_generation'),source_metadata=p.get('source_metadata'),
                    bids=q.get('bids'),asks=q.get('asks'))
                prior[token]=state
            previous_eid=eid
    finally:c.close()
    assert before==(path.stat().st_size,path.stat().st_mtime_ns)
    return dict(path=str(path),prefix_limit=limit,counts=dict(counts),examples=examples,source_stat_unchanged=True,
        use='technical normalization evidence only; no external queue replenishment proven')
