"""Additional provenance only: observation identity is not liquidity replenishment."""
import json,sqlite3
from collections import Counter
from pathlib import Path
from .core import digest,file_hash
from .depth_empirical import unpack


def identities(path,limit=1000):
    path=Path(path);before=(path.stat().st_size,path.stat().st_mtime_ns)
    if Path(str(path)+'-wal').exists() and Path(str(path)+'-wal').stat().st_size:raise ValueError('ACTIVE_WAL')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    rows=[];prior={};counts=Counter()
    try:
        for eid,gen,market,payload in db.execute("select event_id,generation,market_slug,payload_json from events where kind='BOOK' and market_duration='5m' order by event_id limit ?",(limit,)):
            p=unpack(payload);metadata=p.get('source_metadata',[])
            types=[x.get('event_type',x.get('type')) for x in metadata]
            for side in ('up','down'):
                q=p[side];token=q['token_id'];scope=(market,gen,token);old=prior.get(scope)
                meta=[q.get(k) for k in ('event_ts_ms','received_ts_ms','source_hash','sequence')]
                full=any(x.get('event_type')=='book' and x.get('asset_id')==token for x in metadata)
                changed=old is not None and old['_meta']!=meta
                proven=full or ('price_change' in types and changed)
                obs=digest([str(path),eid,market,gen,token])
                state_id=obs if proven else (old['book_state_id'] if old else None)
                depth=digest([q.get('bids'),q.get('asks')])
                r=dict(observation_id=obs,book_state_id=state_id,token=token,market=market,
                    source_timestamp=q.get('event_ts_ms'),receive_timestamp=q.get('received_ts_ms'),
                    envelope_receive_timestamp=p.get('received_ts_ms'),event_type=types,generation=gen,
                    connection_generation=p.get('connection_generation'),exchange_sequence=q.get('sequence'),
                    local_order=eid,best_bid=q.get('bids',[None])[0] if q.get('bids') else None,
                    best_ask=q.get('asks',[None])[0] if q.get('asks') else None,depth_fingerprint=depth,
                    previous_observation_id=old['observation_id'] if old else None,next_observation_id=None,
                    previous_book_state_id=old['book_state_id'] if old else None,next_book_state_id=None,
                    proven_new_token_book_event=proven,same_content_but_new_event=bool(proven and old and old['depth_fingerprint']==depth),
                    identity_basis='explicit full-book token' if full else ('changed token metadata within price_change' if proven else 'no new token mutation proven'),
                    _meta=meta)
                if old:old['next_observation_id']=obs;old['next_book_state_id']=state_id
                prior[scope]=r;rows.append(r)
                counts['token_observations']+=1
                counts['proven_new_token_book_events']+=int(proven)
                counts['same_content_but_new_event']+=int(r['same_content_but_new_event'])
                counts['new_token_event_not_proven']+=int(not proven)
        for r in rows:del r['_meta']
    finally:db.close()
    assert before==(path.stat().st_size,path.stat().st_mtime_ns)
    return dict(source=str(path),prefix_limit=limit,counts=dict(counts),rows=rows,source_stat_unchanged=True,
                limitations=['Prefix only; next pointers are retrospective diagnostics, never decision inputs.',
                 'Observation IDs include source path, local order, market, generation and token, not depth content alone.',
                 'Price_change stripped metadata cannot prove an identical token update; absence of proof is not proof of absence.',
                 'No observed external snapshot proves remaining depth after counterfactual simulated fills.'])


def opportunities(previous):
    old=json.loads(Path(previous).read_text());rows=[]
    for r in old['opportunities']:
        f=r.get('historical_fill') or {}
        rows.append(dict(opportunity_id=r['opportunity_id'],signal_ts=r['signal_ts'],
            entry_due_ts=r['signal_ts']+250,entry_due_ts_kind='nominal target only, not actual entry',
            entry_observation_ts=None,token=r.get('token'),book_state_id=None,book_source_ts=None,
            book_receive_ts=None,previous_book_state_id=None,next_book_state_id=None,
            same_state_as_previous_opportunity=None,new_book_event_since_previous_opportunity=None,
            elapsed_ms=r.get('elapsed_since_previous_opportunity_ms'),requested_qty=None,
            requested_notional=25,simulated_fill_qty=f.get('shares'),
            fill_qty_provenance='historical aggregate only' if f else 'no aggregate fill',
            reason=r['reason']))
    return dict(source=str(previous),source_sha256=file_hash(previous),total_opportunities=len(rows),
        identifiable_opportunities=0,unidentifiable_opportunities=len(rows),same_state_reuse=None,
        new_state_between_opportunities=None,same_content_but_new_event=None,same_state_same_token_reuse=None,
        overlapping_opportunities=None,unknown_cases=len(rows),opportunities=rows)


def compare_three_contracts():
    # Explicit offline mathematical examples. No convention is adopted or fitted.
    return dict(units='shares; asks .5 x 50, requests FIXED25',economic_selection_metrics_used=False,
      same_state_twice={'MODEL_A_V1_REUSABLE_SNAPSHOT':[50,50],'MODEL_B_PERSISTENT_CONSUMPTION':[50,0],'MODEL_C_RESET_ON_PROVEN_NEW_BOOK_STATE':[50,0]},
      identical_content_distinct_proven_event={'MODEL_A_V1_REUSABLE_SNAPSHOT':[50,50],'MODEL_B_PERSISTENT_CONSUMPTION':[50,0],'MODEL_C_RESET_ON_PROVEN_NEW_BOOK_STATE':[50,50]},
      time_only_same_state={'MODEL_A_V1_REUSABLE_SNAPSHOT':[50,50],'MODEL_B_PERSISTENT_CONSUMPTION':[50,0],'MODEL_C_RESET_ON_PROVEN_NEW_BOOK_STATE':[50,0]},
      empirical_effect_on_V1_opportunities=None,classification='DEPTH_MODEL_NOT_IDENTIFIABLE_FROM_CURRENT_EVIDENCE',
      reason='New external observation is distinguishable, but cannot identify counterfactual replenishment or missing actual V1 entry clocks. C would also change V1 decisions on same-state reuse.')
