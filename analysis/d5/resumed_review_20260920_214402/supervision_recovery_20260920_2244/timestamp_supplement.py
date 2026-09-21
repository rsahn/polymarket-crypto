"""Supplementary timestamp audit on the original closed D5 database, streaming read-only."""
import json,pathlib,time,os,datetime,argparse
from sqlite_tuning import connect_ro
from run_accelerated import process_alive
QUERY="""SELECT e.event_id,e.kind,e.market_duration,e.market_slug,e.condition_id,e.generation,
 e.event_ts_ms,e.received_ts_ms,e.available_ts_ms,b.side,b.token_id,b.event_ts_ms,b.received_ts_ms
 FROM events e LEFT JOIN book_sides b USING(event_id)
 WHERE e.session_id=? AND e.kind IN ('BOOK','BTC') ORDER BY e.event_id"""

def scan(rows,progress=None):
 previous={};high={};counts={};examples=[];feeds={};markets={};last_id=None;joined=0;events=0;last_global=None;avail_regressions=0
 def timestamp(key,kind,value,event_id):
  c=counts.setdefault(kind,{'observations':0,'missing':0,'previous_regressions':0,'below_high_water':0,'worst_regression_ms':0})
  c['observations']+=1
  if value is None:c['missing']+=1;return
  old=previous.get(key);ceiling=high.get(key);bad=old is not None and value<old
  c['previous_regressions']+=int(bad);c['below_high_water']+=int(ceiling is not None and value<ceiling)
  if bad:
   c['worst_regression_ms']=max(c['worst_regression_ms'],old-value)
   if len(examples)<100:examples.append({'event_id':event_id,'kind':kind,'identity_generation_side':list(key),'previous_ms':old,'current_ms':value,'regression_ms':old-value})
  previous[key]=value;high[key]=value if ceiling is None else max(ceiling,value)
 def gap(container,key,received):
  r=container.setdefault(key,{'events':0,'first_ms':received,'last_ms':received,'max_gap_ms':0,'gaps_over_5s':0,'gap_time_ms':0,'receive_regressions':0,'examples':[]})
  delta=received-r['last_ms']
  if r['events']:
   r['max_gap_ms']=max(r['max_gap_ms'],delta);r['receive_regressions']+=int(delta<0)
   if delta>5000:
    r['gaps_over_5s']+=1;r['gap_time_ms']+=delta
    if len(r['examples'])<100:r['examples'].append({'from_ms':r['last_ms'],'to_ms':received,'gap_ms':delta})
  r['events']+=1;r['last_ms']=received
 for row in rows:
  eid,kind,duration,slug,condition,generation,event_ts,received,available,side,token,side_source,side_received=row
  joined+=1;identity=(kind,duration,condition,slug,generation)
  if eid!=last_id:
   if last_id is not None and eid<last_id:raise ValueError('INPUT_NOT_IN_EVENT_ID_ORDER')
   events+=1;last_id=eid
   timestamp(('event_source',)+identity,kind+'_SOURCE',event_ts,eid)
   if last_global is not None:avail_regressions+=int(available<last_global)
   last_global=available;feed=duration if kind=='BOOK' else 'BTC';gap(feeds,feed,received)
   if kind=='BOOK':gap(markets,slug,received)
  if kind=='BOOK' and side is not None:
   timestamp(('side_source',)+identity+(side,token),'BOOK_SIDE_SOURCE',side_source,eid)
   timestamp(('side_receive',)+identity+(side,token),'BOOK_SIDE_RECEIVE',side_received,eid)
  if progress and joined%10000==0:progress(joined,events)
 return {'joined_rows':joined,'accepted_events':events,'timestamp_checks':counts,'examples':examples,'accepted_available_regressions':avail_regressions,'feed_gaps':feeds,'market_gaps':markets}

def run(review):
 review=pathlib.Path(review).resolve();state=json.loads((review/'progress.json').read_text(encoding='utf-8'))
 if state['status']=='RUNNING' or process_alive(state['pid']):raise RuntimeError('Review must exit before supplement')
 witness=json.loads((review/'SOURCE_HASH_VERIFICATION.json').read_text())
 if witness['status']!='PASS':raise RuntimeError('Source and code SHA attestation required')
 if (review/'TIMESTAMP_SUPPLEMENT.json').exists():raise FileExistsError('Preserve existing supplement')
 checkpoint=review/'supplement_progress.json'
 if checkpoint.exists():
  old=json.loads(checkpoint.read_text())
  if old.get('status')=='RUNNING' and process_alive(old['pid']):raise RuntimeError('Supplement already active')
 report=json.loads((review/'DATA_QUALITY_REPORT.json').read_text());source=pathlib.Path(witness['source']);before=(source.stat().st_size,source.stat().st_mtime_ns)
 manifest=json.loads((review/'RUN_MANIFEST.json').read_text())
 if list(before)!=manifest['source_stat_before']:raise RuntimeError('Source changed since attestation')
 total=2*report['ROWS']+report['BTC_TICKS'];start=time.monotonic();last=[0.];current=[0,0]
 def update(joined=None,events=None,status='RUNNING',error=None):
  if joined is not None:current[:]=[joined,events]
  now=time.monotonic()
  if status=='RUNNING' and now-last[0]<1:return
  last[0]=now;value={'pid':os.getpid(),'status':status,'step':5,'stage':'Supplement accepted timestamps / gaps, original source','sql':QUERY,'rows_processed':current[0],'accepted_events':current[1],'total_rows':total,'percent':100*current[0]/total if total else None,'rows_per_second':current[0]/max(.001,now-start),'elapsed_seconds':now-start,'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':error}
  tmp=checkpoint.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(checkpoint)
 update()
 db=connect_ro(source.resolve().as_uri()+'?mode=ro');db.set_progress_handler(lambda:(update(),0)[1],100000)
 try:
  result=scan(db.execute(QUERY,(report['SESSION']['session_id'],)),update);result['duration_seconds']=time.monotonic()-start
  result['source_sha256_attestation']=witness['source_sha256'];result['source_stat_unchanged']=before==(source.stat().st_size,source.stat().st_mtime_ns)
  result['coverage_matches']=result['joined_rows']==total and result['accepted_events']==report['ROWS']+report['BTC_TICKS']
  start_ms=report['SESSION']['started_at_ms'];end_ms=report['COLLECTION_STOP_TS_MS']
  for row in result['feed_gaps'].values():row.update(coverage_seconds=(row['last_ms']-row['first_ms'])/1000,initial_gap_ms=max(0,row['first_ms']-start_ms),trailing_gap_ms=max(0,end_ms-row['last_ms']))
  result['feed_gaps_equal_quality']=result['feed_gaps']==report['FEED_GAPS']
  result['definitions']={'previous_regression':'Current accepted source timestamp < previous non-null timestamp in same kind/market/condition/generation; side checks include side/token. Equal values allowed.','below_high_water':'Current timestamp below maximum previously seen within same scope, counts repeated stale observations.','generation_reset':'Each generation is separate; no artificial regression across reconnection generations.','timestamps_changed':False}
  with (review/'TIMESTAMP_SUPPLEMENT.json').open('x') as f:json.dump(result,f,indent=2)
  update(result['joined_rows'],result['accepted_events'],'COMPLETE')
  if not all(result[k] for k in ('source_stat_unchanged','coverage_matches','feed_gaps_equal_quality')):raise RuntimeError('SUPPLEMENT_CONSISTENCY_FAILURE')
  return result
 except BaseException as exc:update(status='ERROR',error=repr(exc));raise
 finally:db.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--review',type=pathlib.Path,required=True);a=p.parse_args();run(a.review)
