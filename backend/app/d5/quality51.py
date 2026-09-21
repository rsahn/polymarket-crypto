"""D5.1 prospective supplement and gate. Historical quality.py is immutable."""
from collections import Counter
import json
from .protocol51 import classify_gap,gap_failure,ntp_gate
from .store import decode


def supplement(db,session,started,stopped,progress=None):
    db.row_factory=__import__('sqlite3').Row
    markets={r['market_slug']:dict(r) for r in db.execute('SELECT * FROM markets')}
    state={}; times={}; activated=set(); rotations=set(); reconnects=set()
    failures=Counter(); classifications=Counter(); gaps=[]; rows=0; envelopes=0; sides=0; btc=0
    wire_previous={};wire_regressions=0;wire_worst=0;wire_missing=0;reconnect_attempts=0;reconnect_markers=0
    stop_markers=0;end_markers=0
    def add_gap(feed,kind,a,b,verified=False,reconnected=False):
        elapsed=b-a;failure=gap_failure(kind,elapsed,transition_verified=verified)
        if elapsed>5000 or kind in ('STARTUP_GAP','SHUTDOWN_GAP','TRANSITION_GAP','RECONNECT_GAP') or failure:
            item=dict(feed=feed,kind=kind,from_ms=a,to_ms=b,gap_ms=elapsed,transition_verified=verified,reconnect_observed=reconnected,failure=failure)
            gaps.append(item);classifications[kind]+=1
        if failure:failures[failure]+=1
    for row in db.execute('''SELECT e.*,u.event_ts_ms AS up_source,u.received_ts_ms AS up_receive,
        d.event_ts_ms AS down_source,d.received_ts_ms AS down_receive
        FROM events e LEFT JOIN book_sides u ON e.event_id=u.event_id AND u.side='UP'
        LEFT JOIN book_sides d ON e.event_id=d.event_id AND d.side='DOWN'
        WHERE e.session_id=? ORDER BY e.event_id''',(session,)):
        rows+=1;kind=row['kind'];feed=row['market_duration'] if kind=='BOOK' else 'BTC';slug=row['market_slug'];gen=row['generation']
        if kind=='ACTIVATE': activated.add((slug,gen))
        if kind=='ROTATION':
            p=decode(row['payload_json']);rotations.add((p.get('previous_slug'),p.get('next_slug')))
        if kind=='RECONNECT':
            reconnects.add(row['market_duration']);reconnect_markers+=1
            reconnect_attempts+=int('reason' in decode(row['payload_json']))
        if kind=='COLLECTION_STOP':
            stop_markers+=1
            if row['received_ts_ms']!=stopped:failures['STOP_TIMESTAMP_MISMATCH']+=1
        if kind=='SESSION_END':
            end_markers+=1
            if decode(row['payload_json']).get('cleanup_errors'):failures['CLEANUP_ERRORS']+=1
        if kind=='BTC_RECONNECT':reconnects.add('BTC')
        if kind not in ('BOOK','BTC'):continue
        if row['received_ts_ms']>stopped or row['available_ts_ms']>stopped:failures['ACCEPTED_AFTER_COLLECTION_STOP']+=1
        current=dict(slug=slug,generation=gen,received=row['received_ts_ms'])
        previous=state.get(feed)
        if previous is None:add_gap(feed,'STARTUP_GAP',started,row['received_ts_ms'])
        else:
            label=classify_gap(previous,current,reconnect=feed in reconnects)
            verified=False
            if label=='TRANSITION_GAP':
                old=markets[previous['slug']];new=markets[slug];duration=300000 if feed=='5m' else 900000
                verified=(old['market_duration']==new['market_duration']==feed and
                    old['expiry_ts_ms']==new['expiry_ts_ms']-duration and
                    previous['received']<old['expiry_ts_ms']<=row['received_ts_ms'] and
                    (slug,gen) in activated and (previous['slug'],slug) in rotations)
            add_gap(feed,label,previous['received'],row['received_ts_ms'],verified,feed in reconnects)
        state[feed]=current;reconnects.discard(feed)
        p=decode(row['payload_json'])
        def ordered(key,value):
            if value is None:failures['MISSING_TIMESTAMP']+=1;return
            if key in times and value<times[key]:failures[key[0]+'_REGRESSION']+=1
            times[key]=value
        ordered(('AVAILABLE',),row['available_ts_ms'])
        if kind=='BTC':
            btc+=1;ordered(('BTC_SOURCE',),row['event_ts_ms']);continue
        envelopes+=1
        if p.get('timestamp_contract')!='D5.1':failures['WRONG_TEMPORAL_CONTRACT']+=1
        values=[p[x].get('event_ts_ms') for x in ('up','down')]
        expected=max(values) if all(x is not None for x in values) else None
        if expected is None or row['event_ts_ms']!=expected or p.get('book_state_source_ts_ms')!=expected or p.get('event_ts_ms')!=expected:failures['BOOK_STATE_TIMESTAMP_MISMATCH']+=1
        if p.get('received_ts_ms')!=row['received_ts_ms']:failures['RECEIPT_MISMATCH']+=1
        if 'wire_event_ts_ms' not in p or not isinstance(p.get('source_metadata'),list):failures['RAW_WIRE_METADATA_MISSING']+=1
        metadata=p.get('source_metadata') or []
        if isinstance(metadata,list) and metadata and isinstance(metadata[-1],dict):
            last=metadata[-1];raw=last.get('timestamp',last.get('event_ts_ms',last.get('ts')))
            try:raw=int(raw) if raw is not None else None
            except (ValueError,TypeError):
                raw=None;failures['RAW_TIMESTAMP_UNPARSABLE']+=1
            if p.get('wire_event_ts_ms')!=raw:failures['WIRE_RAW_TIMESTAMP_MISMATCH']+=1
            if raw is None:wire_missing+=1
            else:
                key=(slug,gen);prior=wire_previous.get(key)
                if prior is not None and raw<prior:
                    wire_regressions+=1;wire_worst=max(wire_worst,prior-raw)
                wire_previous[key]=raw
        else:failures['RAW_WIRE_METADATA_MISSING']+=1
        ordered(('BOOK_SOURCE',slug,gen),row['event_ts_ms'])
        for side in ('up','down'):
            sides+=1;q=p[side]
            if row[side+'_source']!=q.get('event_ts_ms') or row[side+'_receive']!=q.get('received_ts_ms'):failures['SQL_SIDE_METADATA_MISMATCH']+=1
            ordered(('SIDE_SOURCE',slug,gen,side),q.get('event_ts_ms'));ordered(('SIDE_RECEIVE',slug,gen,side),q.get('received_ts_ms'))
            if q.get('received_ts_ms',float('inf'))>row['received_ts_ms']:failures['SIDE_RECEIVED_AFTER_ENVELOPE']+=1
        if progress and rows%10000==0:progress(dict(rows_processed=rows,stage='D5.1 timestamp and gap supplement'))
    for feed in ('5m','15m','BTC'):
        if feed not in state:failures['MISSING_FEED_'+feed]+=1
        else:add_gap(feed,'SHUTDOWN_GAP',state[feed]['received'],stopped)
    if stop_markers!=1 or end_markers<1:failures['STOP_MARKERS_MISSING_OR_DUPLICATE']+=1
    # Independent SQL-side metadata must match the persisted raw component metadata.
    # Detailed source/receive regression checks above use raw payloads, not a projection.
    return dict(contract='D5.1',rows=rows,book_events=envelopes,book_sides=sides,btc_events=btc,
                failures=dict(failures),gap_counts=dict(classifications),gaps=gaps,
                wire_regressions_diagnostic_only=wire_regressions,wire_worst_regression_ms=wire_worst,
                wire_missing_timestamp_count=wire_missing,reconnect_event_markers=reconnect_markers,
                reconnect_attempts=reconnect_attempts,collection_stop_markers=stop_markers,session_end_markers=end_markers)


def gate(report,replay_ok,minimum_seconds,supplement_result,clock_samples):
    failures=[x for x in report['SMOKE_FAILURES'] if x!='RECONNECT_NOT_OBSERVED']
    if report['SESSION']['status'] not in ('STOPPED','STOPPED_BY_USER_CLEAN'):failures.append('UNCLEAN_STOP')
    if report['ACTUAL_DURATION_SECONDS']<minimum_seconds:failures.append('DURATION_TOO_SHORT')
    if report['SQLITE_INTEGRITY_CHECK']!=['ok'] or report['FOREIGN_KEY_VIOLATIONS']:failures.append('SQLITE_INTEGRITY_FAILURE')
    for field in ('OPEN_ANCHORS','POST_EXPIRY_ACCEPTED','CROSS_MARKET_VIOLATIONS','MISSING_TOKEN_IDS','AVAILABILITY_REGRESSIONS'):
        if report.get(field,1):failures.append(field)
    for feed in ('5m','15m','BTC'):
        f=report['FEED_GAPS'].get(feed,{})
        if f.get('coverage_seconds',0)<minimum_seconds:failures.append('INSUFFICIENT_COVERAGE_'+feed)
        if f.get('receive_regressions',1):failures.append('RECEIVE_REGRESSION_'+feed)
    for duration in ('5m','15m'):
        if report['ROTATIONS_BY_DURATION'].get(duration,0)<1:failures.append('ROTATION_MISSING_'+duration)
    if not replay_ok:failures.append('REPLAY_FAILED_OR_DIFFERENT')
    if report.get('CODE_CHANGED_DURING_COLLECTION',True):failures.append('CODE_PROVENANCE_CHANGED')
    failures.extend(supplement_result['failures'])
    if supplement_result['rows']!=report['TOTAL_EVENTS']:failures.append('SUPPLEMENT_INCOMPLETE')
    if len(clock_samples)<3:failures.append('NTP_SEQUENCE_INCOMPLETE')
    from datetime import datetime
    try:
        stamps=[datetime.fromisoformat(x['captured_utc']).timestamp()*1000 for x in clock_samples]
        phases=[x['phase'] for x in clock_samples]
        if phases[:2]!=['gate_1','gate_2'] or phases[-1]!='after':failures.append('NTP_PHASE_SEQUENCE_INVALID')
        if len(stamps)<3 or stamps[1]-stamps[0]<30000:failures.append('NTP_CONSECUTIVE_CHECKS_MISSING')
        if any(b<a or b-a>420000 for a,b in zip(stamps,stamps[1:])):failures.append('NTP_CADENCE_FAILURE')
        if stamps[1]>report['SESSION']['started_at_ms'] or report['SESSION']['started_at_ms']-stamps[1]>120000:failures.append('NTP_PREFLIGHT_NOT_FRESH')
        if stamps[-1]<report['COLLECTION_STOP_TS_MS'] or stamps[-1]-report['COLLECTION_STOP_TS_MS']>120000:failures.append('NTP_POSTFLIGHT_NOT_FRESH')
    except (KeyError,ValueError,TypeError,IndexError):failures.append('NTP_TIMESTAMPS_INVALID')
    for sample in clock_samples:failures.extend(ntp_gate(sample))
    return sorted(set(failures))
