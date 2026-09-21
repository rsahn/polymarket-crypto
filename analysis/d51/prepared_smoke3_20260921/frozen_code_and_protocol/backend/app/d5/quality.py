"""Post-collection data quality only; no strategy selection or research."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .audit import audit
from .replay import NoTrade, replay_database
from .store import decode, encode


def feed_gaps(db, session_id, started, ended):
    """Streaming scan includes boundaries and rotations, not only gaps within a slug."""
    state = {}
    for kind, duration, received in db.execute(
        "SELECT kind,market_duration,received_ts_ms FROM events "
        "WHERE session_id=? AND kind IN ('BOOK','BTC') ORDER BY event_id", (session_id,)
    ):
        feed = duration if kind == 'BOOK' else 'BTC'
        row = state.setdefault(feed, {'events':0, 'first_ms':received, 'last_ms':received,
            'max_gap_ms':0, 'gaps_over_5s':0, 'gap_time_ms':0, 'receive_regressions':0,
            'examples':[]})
        gap = received-row['last_ms']
        if row['events']:
            row['max_gap_ms'] = max(row['max_gap_ms'], gap)
            row['receive_regressions'] += int(gap < 0)
            if gap > 5000:
                row['gaps_over_5s'] += 1
                row['gap_time_ms'] += gap
                if len(row['examples']) < 100:
                    row['examples'].append({'from_ms':row['last_ms'],'to_ms':received,'gap_ms':gap})
        row['events'] += 1
        row['last_ms'] = received
    for row in state.values():
        row['coverage_seconds'] = (row['last_ms']-row['first_ms'])/1000
        row['initial_gap_ms'] = max(0,row['first_ms']-started)
        row['trailing_gap_ms'] = max(0,ended-row['last_ms'])
    return state


def quality_gate(report, replay_ok, minimum_seconds=86400):
    # Reconnection resilience was established by the smoke; zero disconnects is not a fault.
    failures = [item for item in report['SMOKE_FAILURES'] if item != 'RECONNECT_NOT_OBSERVED']
    if report['SESSION']['status'] != 'STOPPED': failures.append('UNCLEAN_STOP')
    if report['ACTUAL_DURATION_SECONDS'] < minimum_seconds: failures.append('DURATION_BELOW_24H')
    if report['SQLITE_INTEGRITY_CHECK'] != ['ok'] or report['FOREIGN_KEY_VIOLATIONS']:
        failures.append('SQLITE_INTEGRITY_FAILURE')
    if report['OPEN_ANCHORS']: failures.append('OPEN_ANCHORS')
    if report['POST_EXPIRY_ACCEPTED']: failures.append('POST_EXPIRY_ACCEPTED')
    for name in ('5m','15m','BTC'):
        feed = report['FEED_GAPS'].get(name)
        if not feed or feed['coverage_seconds'] < minimum_seconds:
            failures.append('INSUFFICIENT_COVERAGE_'+name)
        if feed and (feed['gaps_over_5s'] or feed['initial_gap_ms']>10000 or feed['trailing_gap_ms']>10000):
            failures.append('GAPS_REQUIRE_REVIEW_'+name)
        if feed and feed['receive_regressions']:
            failures.append('RECEIVE_CLOCK_REGRESSION_'+name)
    if not replay_ok: failures.append('REPLAY_FAILED_OR_DIFFERENT')
    if report.get('CODE_CHANGED_DURING_COLLECTION'): failures.append('CODE_PROVENANCE_CHANGED')
    return sorted(set(failures))


def write_new(path, payload):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(payload,f,indent=2,allow_nan=False)


def review(path, output, session_id, *, minimum_seconds=86400, progress=None, final_code_version=None):
    """Called only after the collector exits. All database access is read-only."""
    output = Path(output)
    report = audit(path, session_id)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA temp_store=FILE')
        report['SQLITE_INTEGRITY_CHECK'] = [row[0] for row in db.execute('PRAGMA integrity_check')]
        report['FOREIGN_KEY_VIOLATIONS'] = [list(row) for row in db.execute('PRAGMA foreign_key_check')]
        report['OPEN_ANCHORS'] = db.execute("SELECT count(*) FROM anchors WHERE session_id=? AND status='OPEN'",(session_id,)).fetchone()[0]
        end = db.execute("SELECT payload_json FROM events WHERE session_id=? AND kind='SESSION_END' ORDER BY event_id DESC LIMIT 1",(session_id,)).fetchone()
        end_payload = decode(end[0]) if end else {}
        report['ACTUAL_DURATION_SECONDS'] = end_payload.get('collection_seconds',end_payload.get('elapsed_seconds',0))
        report['SESSION_ELAPSED_SECONDS'] = end_payload.get('elapsed_seconds',0)
        session = report['SESSION']
        report['WALL_DURATION_SECONDS'] = ((session['ended_at_ms'] or session['started_at_ms'])-session['started_at_ms'])/1000
        report['POST_EXPIRY_ACCEPTED'] = db.execute("""SELECT count(*) FROM events e
            JOIN markets m USING(condition_id,market_slug) WHERE e.session_id=? AND e.kind='BOOK'
            AND (e.received_ts_ms>=m.expiry_ts_ms OR e.available_ts_ms>=m.expiry_ts_ms
                 OR e.event_ts_ms>=m.expiry_ts_ms OR EXISTS(SELECT 1 FROM book_sides b
                    WHERE b.event_id=e.event_id AND (b.event_ts_ms>=m.expiry_ts_ms OR b.received_ts_ms>=m.expiry_ts_ms)))""",(session_id,)).fetchone()[0]
        rotations = {'5m':0,'15m':0}
        previous = {}
        for duration, slug in db.execute("SELECT market_duration,market_slug FROM events WHERE session_id=? AND kind='ACTIVATE' ORDER BY event_id",(session_id,)):
            if duration in previous and previous[duration]!=slug: rotations[duration]+=1
            previous[duration]=slug
        report['ROTATIONS_BY_DURATION'] = rotations
        report['ROTATIONS'] = sum(rotations.values())
        report['RECONNECTIONS'] = {'polymarket':report['KINDS'].get('RECONNECT',0),
                                 'binance':report['KINDS'].get('BTC_RECONNECT',0)}
        report['REJECTED_EVENTS'] = sum(report['REJECTIONS'].values())
        report['OUT_OF_ORDER_REJECTED'] = report['REJECTIONS'].get('OUT_OF_ORDER',0)
        collection_stop = end_payload.get('collection_stop_ts_ms',session['ended_at_ms'] or session['started_at_ms'])
        report['COLLECTION_STOP_TS_MS'] = collection_stop
        report['FEED_GAPS'] = feed_gaps(db,session_id,session['started_at_ms'],collection_stop)
    report['CODE_CHANGED_DURING_COLLECTION'] = final_code_version is not None and final_code_version!=report['SESSION']['code_version']
    report['RESEARCH_ALLOWED'] = False
    report['RESEARCH_REASON'] = 'Quality review only; D5 Research is not authorized and will not be started.'
    write_new(output/'DATA_QUALITY_REPORT.json',report)
    results=[]
    for number in (1,2):
        digest=hashlib.sha256()
        count=0
        def sink(record):
            nonlocal count
            digest.update((encode(record)+'\n').encode('utf-8'))
            count+=1
            if progress and count%100000==0:
                progress({'phase':'REPLAY','replay':number,'events_replayed':count})
        result=replay_database(path,session_id,NoTrade(),capital=500.,decision_sink=sink)
        entry={'replay':number,'event_count':count,'decision_sha256':digest.hexdigest(),
               'result_sha256':hashlib.sha256(encode(result).encode('utf-8')).hexdigest(),
               'result':result}
        write_new(output/f'REPLAY_{number}.json',entry)
        results.append(entry)
    same = all(results[0][key]==results[1][key] for key in ('event_count','decision_sha256','result_sha256','result'))
    inert = all(r['result']['metrics']['number_of_orders']==0 and r['result']['metrics']['number_of_fills']==0
                and r['result']['metrics']['final_cash']==500 and not r['result']['metrics']['paired_qty']
                and not r['result']['metrics']['directional_up'] and not r['result']['metrics']['directional_down'] for r in results)
    complete = all(r['event_count']==report['TOTAL_EVENTS'] for r in results)
    report['REPLAYS']=[{k:v for k,v in r.items() if k!='result'} for r in results]
    report['REPLAY_HASHES_EQUAL']=same
    report['NO_TRADE_VERIFIED']=inert
    report['QUALITY_FAILURES']=quality_gate(report,same and inert and complete,minimum_seconds)
    report['QUALITY_REVIEW_PASSED']=not report['QUALITY_FAILURES']
    report['MINIMUM_DURATION_SECONDS']=minimum_seconds
    report['GAP_REVIEW_POLICY']='Any feed gap >5 seconds or endpoint gap >10 seconds requires manual quality review; never silently excused.'
    write_new(output/'FINAL_DATA_QUALITY_REPORT.json',report)
    with (output/'FINAL_DATA_QUALITY_REPORT.md').open('x',encoding='utf-8') as f:
        f.write('# D5 SHADOW — DATA QUALITY REPORT\n\n')
        for key in ('ACTUAL_DURATION_SECONDS','WALL_DURATION_SECONDS','TOTAL_EVENTS','ROWS','5M_MARKETS','15M_MARKETS',
                    'ROTATIONS_BY_DURATION','RECONNECTIONS','CROSS_MARKET_VIOLATIONS','POST_EXPIRY_ACCEPTED',
                    'MISSING_TOKEN_IDS','REJECTED_EVENTS','OUT_OF_ORDER_REJECTED','SQLITE_INTEGRITY_CHECK',
                    'FOREIGN_KEY_VIOLATIONS','OPEN_ANCHORS','REPLAY_HASHES_EQUAL','NO_TRADE_VERIFIED',
                    'QUALITY_REVIEW_PASSED','QUALITY_FAILURES','RESEARCH_ALLOWED'):
            f.write(f'- {key}: {encode(report[key])}\n')
        f.write('\n## Gaps, including rotations and session boundaries\n\n```json\n'+json.dumps(report['FEED_GAPS'],indent=2)+'\n```\n')
        f.write('\n## Replays\n\n```json\n'+json.dumps(report['REPLAYS'],indent=2)+'\n```\n')
        f.write('\nNo D5 Research was started. Source and reception timestamps were not corrected or backfilled.\n')
    return report
