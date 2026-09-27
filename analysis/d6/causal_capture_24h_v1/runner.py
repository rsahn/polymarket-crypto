"""Public-only 24h technical capture. No account SDK, no economic partition loader."""
import argparse,asyncio,json,shutil,sys,time,types,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))
from analysis.d6.causal_capture_24h_v1.collector import Journal,BookCapture,Fixed25Ledger,build_v1,source_seal,storage_preflight,VERSION
from analysis.d6.prospective_v1.core import safety,write_once
DURATION=86400
MAX_INGRESS_BYTES=8*1024**2
MAX_WIRE=1024**2
EXPECTED={'analysis/run_d6_paper_live.py':'a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405','analysis/d6/paper_live.py':'5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364','analysis/d6/prospective_24h_v1/PROTOCOL.json':'ae8dfbd188fe21537ec64c233af0780ce13e3fa0b4e88d984c3ee193f436dfb6'}
def ms():return time.time_ns()//1000000
class Ingress:
 def __init__(self):self.queue=asyncio.Queue(maxsize=1024);self.bytes=0
 def put(self,kind,payload,received=None):
  size=len(json.dumps(payload,separators=(',',':')).encode())
  if size>MAX_WIRE or self.bytes+size>MAX_INGRESS_BYTES or self.queue.full():raise BufferError('INGRESS_OVERFLOW_CAPTURE_INVALID')
  self.queue.put_nowait((kind,payload,ms() if received is None else received,size));self.bytes+=size
 async def get(self):
  k,p,t,n=await self.queue.get();self.bytes-=n;return k,p,t

def checked_seal():
 seal=source_seal(ROOT)
 if any(seal.hashes.get(k)!=v for k,v in EXPECTED.items()):raise ValueError('HISTORICAL_STRATEGY_OR_PROTOCOL_HASH_CHANGED')
 return seal

async def binance(queue):
 import websockets
 while True:
  queue.put('STATUS',{'feed':'BTC','kind':'CONNECT'})
  try:
   async with websockets.connect('wss://data-stream.binance.vision/stream?streams=btcusdt@aggTrade/btcusdt@bookTicker',max_size=MAX_WIRE,max_queue=16,ping_interval=20) as ws:
    async for raw in ws:
     received=ms();queue.put('BTC',json.loads(raw),received)
  except (OSError,websockets.exceptions.WebSocketException,TimeoutError) as e:
   queue.put('STATUS',{'feed':'BTC','kind':'RECONNECT','error':type(e).__name__});await asyncio.sleep(1)

async def polymarket(queue):
 import websockets
 from app.collectors.polymarket import PolymarketMarketDiscovery
 async def heartbeat(ws):
  while True:await asyncio.sleep(10);await ws.send('PING')
 while True:
  markets=await asyncio.to_thread(PolymarketMarketDiscovery.get_active_btc_markets,verify_tls=True,raise_errors=True)
  market=next((m for m in markets if m['market_key']=='5m' and m.get('expiry_ts_ms') is not None and m['expiry_ts_ms']>ms()),None)
  if not market:
   queue.put('STATUS',{'kind':'DISCOVERY_EMPTY'});await asyncio.sleep(3);continue
  # Discovery returns token_ids UP/DOWN and authoritative market identity.
  queue.put('ACTIVATE',market)
  try:
   async with websockets.connect('wss://ws-subscriptions-clob.polymarket.com/ws/market',max_size=MAX_WIRE,max_queue=16,ping_interval=20) as ws:
    await ws.send(json.dumps({'assets_ids':list(market['token_ids'].values()),'type':'market','custom_feature_enabled':True}))
    hb=asyncio.create_task(heartbeat(ws))
    try:
     while ms()<market['expiry_ts_ms']:
      raw=await asyncio.wait_for(ws.recv(),timeout=min(25,max(.01,(market['expiry_ts_ms']-ms())/1000)))
      received=ms()
      if raw in ('PONG','pong','0'):continue
      queue.put('BOOK',json.loads(raw),received)
    finally:hb.cancel();await asyncio.gather(hb,return_exceptions=True)
  except (OSError,websockets.exceptions.WebSocketException,TimeoutError) as e:
   queue.put('STATUS',{'kind':'POLY_RECONNECT_OR_EXPIRY','error':type(e).__name__});await asyncio.sleep(1)

async def clock_evidence():
 from app.d5.clock51 import snapshot
 from app.d5.protocol51 import ntp_gate
 value=await asyncio.to_thread(snapshot);failures=ntp_gate(value)
 if failures:raise ValueError('CLOCK_QUALIFICATION_FAILED:'+','.join(failures))
 return value

async def clock_monitor(queue):
 while True:
  await asyncio.sleep(3600)
  queue.put('CLOCK_EVIDENCE',await clock_evidence())

async def capture(destination):
 safety();seal=checked_seal();destination=Path(destination).resolve()
 if not destination.is_relative_to(ROOT):raise ValueError('DESTINATION_OUTSIDE_AUTHORIZED_REPOSITORY')
 parent=destination.parent
 if not parent.is_dir():raise ValueError('DESTINATION_PARENT_REQUIRED')
 capacity=storage_preflight(shutil.disk_usage(parent).free)
 if capacity['status']!='PASS':raise RuntimeError(json.dumps(capacity))
 initial_clock=await clock_evidence()
 destination.mkdir(exist_ok=False);session=uuid.uuid4().hex
 write_once(destination/'MANIFEST.json',{'version':VERSION,'session':session,'mode':'NO_TRADE','duration_seconds':DURATION,'economic_partitions':None,'initial_clock_evidence':initial_clock,'purpose':'CAUSAL_TECHNICAL_OBSERVATION','source_hashes':seal.hashes,'source_seal':seal.hash,'storage':capacity,'fee_policy':'MARKET_FEE_UNQUALIFIED',**safety()})
 j=Journal(destination/'capture.frames',session);book=BookCapture(j);latest={};ledger=Fixed25Ledger(keep_results=False);engine=build_v1(ROOT,j,ledger,latest);queue=Ingress();began=time.monotonic();status='INCOMPLETE';error=None;last_checkpoint=began;last_receive=None
 tasks=[asyncio.create_task(binance(queue)),asyncio.create_task(polymarket(queue)),asyncio.create_task(clock_monitor(queue))]
 async def apply(kind,payload,received):
  nonlocal last_receive
  if last_receive is not None and received<last_receive:raise ValueError('RECEIVE_CLOCK_REGRESSION')
  last_receive=received
  if kind=='ACTIVATE':
   j.append('RAW',{'kind':'MARKET_METADATA','receive_ts_ms':received,'payload':payload})
   book.activate(payload['slug'],payload['metadata']['conditionId'],payload['token_ids'],payload['expiry_ts_ms'])
  elif kind=='BOOK':
   snap=book.ingest(payload,received)
   if snap and snap.get('book_generation_ready'):await engine['on_quote']('5m',snap)
  elif kind=='BTC':
   j.append('RAW',{'kind':'BINANCE','receive_ts_ms':received,'payload':payload});data=payload.get('data',payload)
   if data.get('e')=='aggTrade':
    if int(data['E'])>received:raise ValueError('FUTURE_BTC_SOURCE_TIMESTAMP')
    await engine['on_btc'](types.SimpleNamespace(event_ts_ms=int(data['E']),recv_ts_ms=received,price=float(data['p'])))
  else:j.append('CONTROL',{'kind':kind,'receive_ts_ms':received,'payload':payload})
 try:
  j.append('CONTROL',{'kind':'SESSION_START','receive_ts_ms':ms(),'seal_hash':seal.hash})
  while time.monotonic()-began<DURATION:
   if engine['failures']:raise engine['failures'][0]
   for task in tasks:
    if task.done():task.result();raise RuntimeError('FEED_ENDED')
   try:k,p,t=await asyncio.wait_for(queue.get(),timeout=.25);await apply(k,p,t)
   except asyncio.TimeoutError:j.flush()
   if time.monotonic()-last_checkpoint>=3600:
    j.checkpoint({'latest_book_refs':book.states,'capital_fixed25':ledger.capital,'pending_opportunities':engine['observer'].opportunities,'policy':'Offline recovery scans verified journal; no live continuation across restart'});last_checkpoint=time.monotonic()
  status='DURATION_REACHED_REQUIRES_ADMISSIBILITY_AUDIT'
 except BaseException as exc:status='INCOMPLETE';error=type(exc).__name__+':'+str(exc);raise
 finally:
  for task in tasks:task.cancel()
  await asyncio.gather(*tasks,return_exceptions=True)
  try:
   if error is None:
    while not queue.queue.empty():k,p,t=await queue.get();await apply(k,p,t)
    if engine['pending']:await asyncio.gather(*engine['pending'])
    await asyncio.sleep(0)
    if engine['failures']:raise engine['failures'][0]
    j.append('CONTROL',{'kind':'FINAL_CLOCK_EVIDENCE','payload':await clock_evidence()})
    seal.verify(ROOT);j.append('CONTROL',{'kind':'SESSION_END','status':status,'receive_ts_ms':ms()})
   else:
    for task in engine['pending']:task.cancel()
    await asyncio.gather(*engine['pending'],return_exceptions=True)
  except BaseException as exc:
   status='INCOMPLETE';error=type(exc).__name__+':'+str(exc);raise
  finally:
   for task in list(engine['pending']):task.cancel()
   await asyncio.gather(*engine['pending'],return_exceptions=True)
   try:j.close()
   except BaseException as exc:status='INCOMPLETE';error=type(exc).__name__+':'+str(exc)
   write_once(destination/'FINAL_STATUS.json',{'status':status,'error':error,'admissible':False,'complete_24h_proven':False,'journal_failed':j.failed,'records':j.seq,'bytes_by_bucket':j.used,**safety()})

def main():
 parser=argparse.ArgumentParser(description='NO_TRADE technical capture; never opens TRAIN/VALIDATION/OOS');parser.add_argument('--preflight',action='store_true');parser.add_argument('--capture',type=Path);a=parser.parse_args()
 safety();checked_seal()
 if a.preflight:print(json.dumps(storage_preflight(shutil.disk_usage(ROOT).free),indent=2));return
 if not a.capture:parser.error('--preflight or explicit --capture required')
 asyncio.run(capture(a.capture))
if __name__=='__main__':main()
