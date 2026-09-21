"""Read-only D5 data quality report; zero violations never substitutes for coverage."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .store import encode, json_text


def audit(path, session='latest'):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.create_function('d5_json',1,json_text,deterministic=True)
    db.execute('BEGIN')
    if [r[0] for r in db.execute('SELECT version FROM schema_info')] not in ([1],[2]):
        raise ValueError('D5 schema 1 or 2 required')
    if session=='latest':
        row=db.execute('SELECT session_id FROM sessions ORDER BY started_at_ms DESC LIMIT 1').fetchone()
        if not row: raise ValueError('No session')
        session=row[0]
    s=db.execute('SELECT * FROM sessions WHERE session_id=?',(session,)).fetchone()
    if not s: raise ValueError('Unknown session')
    # Parameterized temporary views are unavailable; a session CTE prefixes every query.
    prefix='WITH e AS NOT MATERIALIZED (SELECT * FROM events WHERE session_id=?) '
    def rows(sql,params=()):
        return [dict(r) for r in db.execute(prefix+sql,(session,*params))]
    def count(sql): return rows(sql)[0]['n']
    kinds={r['kind']:r['n'] for r in rows('SELECT kind,count(*) n FROM e GROUP BY kind')}
    markets=rows("""SELECT e.market_duration,e.market_slug,e.condition_id,e.token_up,e.token_down,
        count(*) snapshots,min(e.received_ts_ms) first_ms,max(e.received_ts_ms) last_ms,
        max(e.received_ts_ms)-min(e.received_ts_ms) collection_ms,
        count(distinct generation) generations FROM e WHERE kind='BOOK' GROUP BY e.market_slug""")
    cross=count("""SELECT count(*) n FROM e LEFT JOIN markets m USING(condition_id,market_slug)
        WHERE e.kind='BOOK' AND (m.condition_id IS NULL OR e.token_up!=m.token_up OR e.token_down!=m.token_down
        OR e.market_duration!=m.market_duration)""")
    cross+=count("""SELECT count(*) n FROM book_sides b JOIN e USING(event_id)
        WHERE b.token_id != CASE WHEN b.side='UP' THEN e.token_up ELSE e.token_down END""")
    cross+=count("""SELECT count(*) n FROM anchors a JOIN e USING(event_id)
        WHERE a.anchor_market_slug!=e.market_slug OR a.anchor_condition_id!=e.condition_id
        OR a.anchor_token_up!=e.token_up OR a.anchor_token_down!=e.token_down""")
    cross+=count("""SELECT count(*) n FROM hedge_attempts h JOIN e USING(event_id)
        JOIN anchors a ON a.anchor_id=h.anchor_id WHERE h.status='ACCEPT' AND
        (h.hedge_market_slug!=a.anchor_market_slug OR h.hedge_condition_id!=a.anchor_condition_id
        OR h.hedge_token_id!=CASE WHEN a.first_side='UP' THEN a.anchor_token_down ELSE a.anchor_token_up END)""")
    post=count("""SELECT count(*) n FROM e JOIN markets m USING(condition_id,market_slug)
        WHERE kind='BOOK' AND (received_ts_ms>=m.expiry_ts_ms OR available_ts_ms>=m.expiry_ts_ms
        OR event_ts_ms>=m.expiry_ts_ms)""")
    post_anchor=count('SELECT count(*) n FROM anchors a JOIN e USING(event_id) WHERE a.available_ts_ms>=a.expiry_ts_ms')
    post_sides=count("""SELECT count(*) n FROM book_sides b JOIN e USING(event_id)
        JOIN markets m USING(condition_id,market_slug) WHERE e.kind='BOOK'
        AND (b.event_ts_ms>=m.expiry_ts_ms OR b.received_ts_ms>=m.expiry_ts_ms)""")
    incomplete=count("""SELECT count(*) n FROM e WHERE kind='BOOK' AND
        (SELECT count(*) FROM book_sides b WHERE b.event_id=e.event_id)!=2""")
    missing=count("""SELECT count(*) n FROM e WHERE kind='BOOK' AND
        (token_up IS NULL OR token_up='' OR token_down IS NULL OR token_down='')""")
    latency=rows("""SELECT kind,count(*) n,avg(received_ts_ms-event_ts_ms) mean_ms,
        min(received_ts_ms-event_ts_ms) min_ms,max(received_ts_ms-event_ts_ms) max_ms,
        sum(event_ts_ms IS NULL) missing_source_timestamp,
        sum(event_ts_ms>received_ts_ms+2000) clock_ahead_over_2s,
        avg(available_ts_ms-received_ts_ms) mean_processing_ms,
        max(available_ts_ms-received_ts_ms) max_processing_ms
        FROM e WHERE kind IN ('BOOK','BTC') GROUP BY kind""")
    gaps=rows(""", gaps AS (SELECT market_slug,received_ts_ms-lag(received_ts_ms) OVER
        (PARTITION BY market_slug ORDER BY event_id) gap_ms FROM e WHERE kind='BOOK')
        SELECT market_slug,max(gap_ms) max_gap_ms,sum(gap_ms>5000) gaps_over_5s,
        sum(CASE WHEN gap_ms>5000 THEN gap_ms ELSE 0 END) gap_time_ms
        FROM gaps GROUP BY market_slug""")
    depth=rows("""SELECT side,count(*) n,avg(best_ask_qty) mean_ask_qty,min(best_ask_qty) min_ask_qty,
        max(best_ask_qty) max_ask_qty,avg(best_bid_qty) mean_bid_qty,
        sum(best_ask_qty=0) zero_ask_depth,sum(best_bid_qty=0) zero_bid_depth,
        sum(best_ask_qty>0 AND best_ask_qty<10) ask_depth_0_to_10,
        sum(best_ask_qty>=10 AND best_ask_qty<100) ask_depth_10_to_100,
        sum(best_ask_qty>=100 AND best_ask_qty<1000) ask_depth_100_to_1000,
        sum(best_ask_qty>=1000) ask_depth_ge_1000,
        avg(spread) mean_spread FROM book_sides JOIN e USING(event_id) GROUP BY side""")
    rejects={r['reason']:r['n'] for r in rows("SELECT json_extract(d5_json(payload_json),'$.reason') reason,count(*) n FROM e WHERE kind='REJECT' GROUP BY reason")}
    bounds=rows('SELECT min(available_ts_ms) first_ms,max(available_ts_ms) last_ms FROM e')[0]
    regressions=count(""", ordered AS (SELECT available_ts_ms,lag(available_ts_ms) OVER(ORDER BY event_id) previous FROM e)
                         SELECT count(*) n FROM ordered WHERE available_ts_ms<previous""")
    orphan_anchors=count("""SELECT count(*) n FROM anchors a JOIN e USING(event_id)
        WHERE a.status='OPEN' AND a.expiry_ts_ms <= (SELECT max(available_ts_ms) FROM e)""")
    m5=[m for m in markets if m['market_duration']=='5m']
    m15=[m for m in markets if m['market_duration']=='15m']
    failures=[]
    if cross or post or post_anchor or post_sides or incomplete or missing or regressions or orphan_anchors:
        failures.append('INTEGRITY_VIOLATION')
    if not m5 or not m15 or not kinds.get('BTC',0): failures.append('MISSING_FEED_COVERAGE')
    if len(m5)<2: failures.append('5M_ROTATION_NOT_OBSERVED')
    if not any(m['generations']>=2 for m in markets): failures.append('RECONNECT_NOT_OBSERVED')
    if any(x['clock_ahead_over_2s'] for x in latency): failures.append('SOURCE_CLOCK_ANOMALY')
    report={'SESSION':dict(s),'ROWS':kinds.get('BOOK',0),'TOTAL_EVENTS':sum(kinds.values()),
            'REAL_MARKETS':len(markets),'5M_MARKETS':len(m5),'15M_MARKETS':len(m15),
            'CROSS_MARKET_VIOLATIONS':cross,'POST_EXPIRY_EVENTS':post,'POST_EXPIRY_ANCHORS':post_anchor,
            'POST_EXPIRY_BOOK_SIDES':post_sides,'INCOMPLETE_BOOK_EVENTS':incomplete,
            'MISSING_TOKEN_IDS':missing,'AVAILABILITY_REGRESSIONS':regressions,'EXPIRED_OPEN_ANCHORS':orphan_anchors,
            'BTC_TICKS':kinds.get('BTC',0),'RECONNECTS':kinds.get('RECONNECT',0),
            'KINDS':kinds,'REJECTIONS':rejects,'LATENCY':latency,'DEPTH':depth,
            'MARKETS':markets,'GAPS':gaps,'BOUNDS':bounds,
            'SMOKE_VALIDATED':not failures,'SMOKE_FAILURES':failures,
            'RESEARCH_ALLOWED':False,'RESEARCH_REASON':'Separate 24h+ quality review required; no automatic optimization'}
    db.close()
    return report


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=Path(__file__).resolve().parents[3]/'data/d5_live.db')
    parser.add_argument('--session',default='latest')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--require-smoke',action='store_true')
    args=parser.parse_args()
    if args.out and (args.out.resolve()==args.db.resolve() or args.out.exists()):
        parser.error('Output must be a new file, different from the input database')
    report=audit(args.db,args.session)
    if args.out:
        with args.out.open('x',encoding='utf-8') as output:
            json.dump(report,output,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k.isupper() and not isinstance(v,(list,dict))},indent=2))
    print('SMOKE_FAILURES:',report['SMOKE_FAILURES'])
    if args.require_smoke and not report['SMOKE_VALIDATED']:
        raise SystemExit(2)


if __name__=='__main__': cli()
