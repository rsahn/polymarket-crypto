"""D6 public feeds + virtual simulator. No authenticated client or order endpoint."""
import asyncio,datetime,hashlib,json,pathlib,sqlite3,sys,time,os,zlib,urllib.request,shutil
from dataclasses import asdict
HERE=pathlib.Path(__file__).resolve().parent;D6=HERE.parent;ROOT=D6.parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from engine import Engine,Limits,guard,encode
import clock_guard
from app.d5.identity import MarketIdentity
from app.collectors.binance import BinanceCollector
from app.collectors.polymarket import PolymarketMarketDiscovery
from app.collectors.polymarket_ws import PolymarketOrderbookCollector

def write_status(path,payload):
 text=encode(payload);tmp=path.with_suffix('.tmp');tmp.write_text(text,encoding='utf-8')
 for attempt in range(8):
  try:tmp.replace(path);return
  except PermissionError:time.sleep(.02*(attempt+1))
 # Status readers may deny replacement on Windows; journal remains authoritative.
 try:path.write_text(text,encoding='utf-8')
 except OSError:pass

def accept_snapshot(book):
 reason=book.get('reject_reason')
 if reason=='CROSS_MARKET_REJECT' or book.get('stale_token'):raise ValueError('CROSS_MARKET_REJECT')
 return not reason

def now_ms():return time.time_ns()//1000000
def fingerprint(limits):
 files=[HERE/'engine.py',HERE/'runtime.py',HERE/'clock_guard.py',ROOT/'backend/app/collectors/binance.py',ROOT/'backend/app/collectors/polymarket_ws.py',ROOT/'backend/app/collectors/polymarket.py']
 return {'limits':asdict(limits),'code':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
def start_gate():
 guard()
 path=D6/'OFFLINE_VERDICT.json'
 if not path.exists():raise RuntimeError('OFFLINE_VERDICT_REQUIRED')
 verdict=json.loads(path.read_text(encoding='utf-8'))
 if verdict.get('verdict') not in ('EXPERIMENTAL_PAPER_READY','PAPER_READY'):raise RuntimeError('NOT_PAPER_READY:'+verdict.get('verdict','UNKNOWN'))
 if verdict.get('critical_anomalies')!=[] or verdict.get('technical_tests_passed') is not True:raise RuntimeError('TECHNICAL_VALIDATION_REQUIRED')
 audit=ROOT/'analysis/d5/3h_20260920_124822_review/FINAL_DATA_QUALITY_REPORT.json'
 if not audit.exists():raise RuntimeError('WAITING_FOR_D5_AUDIT')
 report=json.loads(audit.read_text(encoding='utf-8'))
 if not report.get('QUALITY_REVIEW_PASSED'):raise RuntimeError('D5_QUALITY_REVIEW_REQUIRED:'+str(report.get('QUALITY_FAILURES')))
 if verdict.get('validated_fingerprint')!=fingerprint(Limits()):raise RuntimeError('VALIDATED_CODE_OR_PARAMETERS_CHANGED')
 return verdict

def public_resolution(condition):
 if not condition.startswith('0x') or len(condition)!=66 or any(c not in '0123456789abcdefABCDEF' for c in condition[2:]):raise ValueError('INVALID_CONDITION')
 url='https://clob.polymarket.com/markets/'+condition
 request=urllib.request.Request(url,headers={'User-Agent':'D6-Paper-Public-Data/1.0'},method='GET')
 with urllib.request.urlopen(request,timeout=15) as response:body=response.read()
 data=json.loads(body)
 if data.get('condition_id')!=condition or not data.get('closed'):return None
 winners=[t for t in data.get('tokens',[]) if t.get('winner') is True]
 if len(winners)!=1 or winners[0].get('outcome','').upper() not in ('UP','DOWN'):return None
 return {'winner':winners[0]['outcome'].upper(),'token_id':str(winners[0]['token_id']),'condition_id':condition,'resolved':True,'url':url,'retrieved_ms':now_ms(),'response_sha256':hashlib.sha256(body).hexdigest(),'response':data}

async def run(out,seconds=86400,limits=None):
 verdict=start_gate();limits=limits or Limits()
 if limits!=Limits():raise RuntimeError('UNVALIDATED_PARAMETER_OVERRIDE')
 out=pathlib.Path(out).resolve()
 out.mkdir(parents=True,exist_ok=False)
 clock=await asyncio.to_thread(clock_guard.check);(out/'CLOCK_PREFLIGHT.json').write_text(encode(clock),encoding='utf-8')
 if not clock['passed']:raise RuntimeError('CLOCK_PREFLIGHT_FAILED')
 db=sqlite3.connect(out/'paper.db');db.execute('CREATE TABLE journal(sequence INTEGER PRIMARY KEY,timestamp_ms INTEGER,kind TEXT,market_slug TEXT,condition_id TEXT,payload BLOB NOT NULL)')
 db.execute('CREATE TABLE session(mode TEXT CHECK(mode="PAPER"),capital TEXT,status TEXT,started_ms INTEGER,ended_ms INTEGER)')
 began_ms=now_ms();began=time.monotonic();db.execute('INSERT INTO session VALUES(?,?,?,?,NULL)',('PAPER','500','RUNNING',began_ms));db.commit()
 def journal(row):
  raw=encode(row).encode();db.execute('INSERT INTO journal VALUES(?,?,?,?,?,?)',(row['sequence'],row['timestamp_ms'],row['kind'],row['market_slug'],row['condition_id'],zlib.compress(raw,1)));db.commit()
 engine=Engine(limits,journal);engine.status='RUNNING';engine.reason='PROSPECTIVE_EXPERIMENT';lock=fingerprint(limits);lock.update(version='D6_EXPERIMENTAL_V1',timestamp_ms=began_ms,features='Causal features in engine.py; 250ms-30s BTC lags, depths, inventory',offline_verdict=verdict)
 (out/'STRATEGY_LOCK.json').write_text(encode(lock),encoding='utf-8')
 initial_fingerprint=fingerprint(limits);active={'key':None,'generation':0};last={'BTC':0,'BOOK':0};curves=[];btc_curve=[];actions=[];failures=[];statusfile=out/'status.json';reason='24H_COMPLETED';status='COMPLETED';daily={};hourly={}
 def snapshot():
  now=now_ms();state=engine.state(now);f=engine.features(active['key'],now) if active['key'] in engine.positions else None
  day=datetime.datetime.fromtimestamp(now/1000,datetime.timezone.utc).strftime('%Y-%m-%d')
  if day not in daily:daily[day]=state['equity'] if daily else __import__('decimal').Decimal(500)
  today=state['equity']-daily[day] if state['equity'] is not None and daily[day] is not None else None
  hour=datetime.datetime.fromtimestamp(now/1000,datetime.timezone.utc).strftime('%Y-%m-%dT%H:00Z')
  if hour not in hourly:hourly[hour]={'first_ms':now,'first_equity':state['equity'],'last_ms':now,'last_equity':state['equity']}
  hourly[hour].update(last_ms=now,last_equity=state['equity'])
  payload={'pnl_today':today,'pnl_today_timezone':'UTC','mode':'PAPER','real_money':False,'status':engine.status,'reason':engine.reason,'pid':os.getpid(),'uptime_seconds':time.monotonic()-began,'timestamp_ms':now,'account':state,'market':engine.identities.get(active['key']),'features':f,'latest_decision':actions[-1] if actions else None,'executions':[{k:v for k,v in o.items() if k!='features'} for o in engine.orders[-30:]],'feeds':{k:{'last_ms':v,'age_ms':now-v if v else None,'status':'OK' if v and now-v<limits.fresh_ms else 'STALE'} for k,v in last.items()},'equity_curve':curves[-1500:],'btc_curve':btc_curve[-1500:],'market_count':len(engine.identities),'failures':failures,'strategy_hash_unchanged':fingerprint(limits)==initial_fingerprint}
  write_status(statusfile,payload);write_status(D6/'paper_status.json',payload)
 async def on_btc(tick):
  engine.tick(tick.price,tick.event_ts_ms,tick.recv_ts_ms,now_ms());last['BTC']=tick.recv_ts_ms
  if not btc_curve or tick.recv_ts_ms-btc_curve[-1][0]>=1000:btc_curve.append([tick.recv_ts_ms,tick.price])
  if len(btc_curve)>20000:del btc_curve[:1000]
 async def btc_status(kind,payload):
  if kind in ('BTC_RECONNECT','BTC_CONNECTED'):engine.btc.clear()
  engine.emit(kind,now_ms(),**payload)
 async def markets():
  while True:
   found=await asyncio.to_thread(PolymarketMarketDiscovery.get_active_btc_markets,verify_tls=True,raise_errors=True)
   market=next((m for m in found if m['market_key']=='5m' and m.get('expiry_ts_ms',0)>now_ms()),None)
   if not market:await asyncio.sleep(2);continue
   metadata=market.get('metadata') or {};schedule=metadata.get('feeSchedule') or {}
   if metadata.get('feesEnabled') is not True or str(schedule.get('rate'))!=limits.fee_rate or schedule.get('exponent')!=1:raise ValueError('FEE_SCHEDULE_UNVERIFIED')
   if float(metadata.get('orderMinSize',5))>float(limits.max_order_qty):raise ValueError('MINIMUM_ORDER_SIZE_CHANGED')
   identity=MarketIdentity.from_market(market);fields=identity.fields();active['generation']+=1;generation=active['generation'];active['key']=identity.condition_id
   sampled=[0]
   async def on_book(book):
    if active['generation']!=generation:return
    if not accept_snapshot(book):return
    now=now_ms()
    if now-sampled[0]<100:return
    sampled[0]=now
    if engine.observe(fields,book,now):last['BOOK']=now
   feed=PolymarketOrderbookCollector('5m',{'UP':identity.token_up,'DOWN':identity.token_down},on_book,identity.expiry_ts_ms,identity=identity)
   task=asyncio.create_task(feed.run())
   try:
    while now_ms()<identity.expiry_ts_ms and not task.done():await asyncio.sleep(.2)
    if task.done():await task
   except (asyncio.CancelledError,ValueError):raise
   except Exception as exc:failures.append({'timestamp_ms':now_ms(),'kind':'BOOK_RECONNECT','error':repr(exc)})
   finally:
    active['generation']+=1;task.cancel();await asyncio.gather(task,return_exceptions=True);engine.books.pop(identity.condition_id,None)
   await asyncio.sleep(.25)
 async def settle_loop():
  while True:
   for key,identity in list(engine.identities.items()):
    if now_ms()<identity['expiry_ts_ms'] or key in engine.settlements:continue
    try:evidence=await asyncio.to_thread(public_resolution,key)
    except Exception as exc:failures.append({'kind':'RESOLUTION_UNAVAILABLE','condition_id':key,'error':repr(exc)});continue
    if evidence:
     if evidence['token_id']!=identity['token_'+evidence['winner'].lower()]:raise RuntimeError('CROSS_MARKET_RESOLUTION')
     engine.settle(key,evidence['winner'],now_ms(),evidence)
   await asyncio.sleep(30)
 async def clock_loop():
  while True:
   await asyncio.sleep(1800);evidence=await asyncio.to_thread(clock_guard.check);engine.emit('CLOCK_CHECK',now_ms(),evidence=evidence)
   if not evidence['passed']:raise RuntimeError('CLOCK_OFFSET_OR_SYNC_FAILURE')
 tasks=[asyncio.create_task(clock_loop()),asyncio.create_task(BinanceCollector('btcusdt',on_btc,btc_status).run()),asyncio.create_task(markets()),asyncio.create_task(settle_loop())]
 last_decision=last_snapshot=0;wall=now_ms();mono=time.monotonic()
 try:
  while time.monotonic()-began<seconds:
   now=now_ms();current_mono=time.monotonic()
   if abs((now-wall)-(current_mono-mono)*1000)>500:raise RuntimeError('CLOCK_ANOMALY')
   wall,mono=now,current_mono
   for task in tasks:
    if task.done():await task;raise RuntimeError('FEED_TASK_EXITED')
   if (out/'STOP_REQUESTED').exists():status='PAUSED';reason='USER_STOP';break
   if time.monotonic()-began>30 and any(not t or now-t>30000 for t in last.values()):raise RuntimeError('PERSISTENT_FEED_LOSS')
   if shutil.disk_usage(out).free<5*1024**3:raise RuntimeError('DISK_RESERVE')
   engine.execute_due(now)
   key=active['key']
   if key in engine.positions and now-last_decision>=1000:
    last_decision=now;decision=engine.decide(key,now);actions.append({'timestamp_ms':now,**decision});actions[:]=actions[-30:];engine.submit(key,decision,now)
   if now-last_snapshot>=1000:
    last_snapshot=now;state=engine.state(now)
    if state['max_drawdown_lower_bound_valuation']>__import__('decimal').Decimal(limits.max_drawdown):raise RuntimeError('MAX_PAPER_DRAWDOWN')
    if fingerprint(limits)!=initial_fingerprint:raise RuntimeError('STRATEGY_CHANGED')
    if not curves or now-curves[-1][0]>=5000:curves.append([now,state['equity'],state['drawdown_lower_bound_valuation']])
    snapshot()
   await asyncio.sleep(.05)
 except BaseException as exc:
  status='FAILED';reason=repr(exc);failures.append({'kind':'CRITICAL','error':reason});raise
 finally:
  for task in tasks:task.cancel()
  await asyncio.gather(*tasks,return_exceptions=True)
  if engine.pending:engine.pending['status']='CANCELLED_ON_STOP';engine.pending=None;engine.reserved=__import__('decimal').Decimal(0)
  engine.status=status;engine.reason=reason
  try:final=engine.state(now_ms())
  except Exception as exc:final={'accounting_error':repr(exc),'cash':engine.cash};status='FAILED';reason='ACCOUNTING_INVARIANT'
  try:
   engine.emit('SESSION_END',now_ms(),status=status,reason=reason,account=final,strategy_hash_unchanged=fingerprint(limits)==initial_fingerprint)
   db.execute('UPDATE session SET status=?,ended_ms=?',(status,now_ms()));db.commit()
  except Exception as exc:status='FAILED';reason='JOURNAL_CLOSE_FAILED';failures.append({'kind':reason,'error':repr(exc)})
  finally:db.close()
  engine.status=status;engine.reason=reason
  try:snapshot()
  except Exception as exc:failures.append({'kind':'FINAL_STATUS_FAILED','error':repr(exc)})
  for h in hourly.values():h['pnl_between_observed_endpoints']=h['last_equity']-h['first_equity'] if h['last_equity'] is not None and h['first_equity'] is not None else None
  latencies=[o['observed_latency_ms'] for o in engine.orders if 'observed_latency_ms' in o]
  regimes={}
  for order in engine.orders:
   momentum=(order.get('features') or {}).get('momentum');regime='UNKNOWN' if momentum is None else 'BTC_UP' if momentum>0.0003 else 'BTC_DOWN' if momentum<-.0003 else 'BTC_FLAT'
   r=regimes.setdefault(regime,{'orders':0,'filled_orders':0,'fees':__import__('decimal').Decimal(0),'turnover':__import__('decimal').Decimal(0),'realized_pnl':None,'pnl_note':'Not attributable without a frozen lot attribution rule; not fabricated'})
   r['orders']+=1;r['filled_orders']+=order['filled_qty']>0;r['fees']+=order.get('fees',0);r['turnover']+=order.get('notional',0)
  report={'performance_by_hour':hourly,'performance_by_regime':regimes,'observed_latency_ms':{'count':len(latencies),'min':min(latencies) if latencies else None,'max':max(latencies) if latencies else None,'mean':sum(latencies)/len(latencies) if latencies else None},'status':status,'reason':reason,'duration_seconds':time.monotonic()-began,'completed_24h':status=='COMPLETED' and time.monotonic()-began>=86400,'account':final,'strategy_hash_unchanged':fingerprint(limits)==initial_fingerprint,'failures':failures,'limitations':'Unresolved or insufficient liquidation depth is UNKNOWN; no fabricated realized profit.'}
  (out/'PAPER_24H_REPORT.json').write_text(encode(report),encoding='utf-8');(out/'PAPER_24H_REPORT.md').write_text('# D6 PAPER — NO REAL MONEY\n\n```json\n'+json.dumps(report,default=str,indent=2)+'\n```\n',encoding='utf-8')
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--seconds',type=int,default=86400);p.add_argument('--authorize-paper-start',action='store_true');a=p.parse_args()
 if not a.authorize_paper_start:p.error('Explicit user authorization required before PAPER start')
 asyncio.run(run(a.out,a.seconds))
