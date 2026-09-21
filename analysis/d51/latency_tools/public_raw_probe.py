"""Bounded public-feed diagnostic; no trading, no source DB, no reconnect."""
import asyncio,base64,datetime,hashlib,json,pathlib,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'analysis/d51/latency_tools')]
import websockets
from app.collectors.polymarket import PolymarketMarketDiscovery
from app.d5.clock51 import snapshot as clock_snapshot
from diagnose import Histogram

def dump(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)

async def observe(market,out):
    duration=market['market_key'];identity=market
    hist=Histogram();frames=0;events=0;errors=[];start=time.monotonic();deadline=start+60
    from app.d5.identity import MarketIdentity
    ident=MarketIdentity.from_market(market)
    subscription={'assets_ids':[ident.token_up,ident.token_down],'type':'market'}
    dump(out/(duration+'_identity.json'),dict(market=market,subscription=subscription))
    async def heartbeat(ws):
        while True:
            await asyncio.sleep(10);await ws.send('PING')
    with (out/(duration+'_raw.jsonl')).open('x',encoding='utf-8',buffering=65536) as log:
        try:
            async with websockets.connect('wss://ws-subscriptions-clob.polymarket.com/ws/market',ping_interval=None,open_timeout=10,close_timeout=2) as ws:
                await ws.send(json.dumps(subscription));hb=asyncio.create_task(heartbeat(ws))
                try:
                    while time.monotonic()<deadline and time.time_ns()//1000000<ident.expiry_ts_ms:
                        try:raw=await asyncio.wait_for(ws.recv(),min(deadline-time.monotonic(),max(.001,(ident.expiry_ts_ms-time.time_ns()//1000000)/1000)))
                        except asyncio.TimeoutError:break
                        recv=time.time_ns()//1000000;mono=time.monotonic_ns();frames+=1
                        log.write(json.dumps(dict(received_ms=recv,monotonic_ns=mono,raw=raw if isinstance(raw,str) else None,raw_base64=base64.b64encode(raw).decode() if isinstance(raw,bytes) else None),separators=(',',':'))+'\n')
                        try:payload=json.loads(raw)
                        except (ValueError,TypeError):continue
                        for event in payload if isinstance(payload,list) else [payload]:
                            if not isinstance(event,dict):continue
                            value=event.get('timestamp');events+=1
                            try:ts=int(value) if value is not None else None
                            except (ValueError,TypeError):ts=None
                            hist.add(recv-ts if ts is not None else None)
                finally:
                    hb.cancel();await asyncio.gather(hb,return_exceptions=True)
        except Exception as exc:errors.append(repr(exc))
    r=dict(feed=duration,frames=frames,event_objects=events,seconds=time.monotonic()-start,errors=errors,wire_age=hist.report(),diagnostic_only=True,not_contemporaneous_with_smoke=True)
    dump(out/(duration+'_summary.json'),r);return r

async def main():
    out=ROOT/'analysis/d51'/('raw_probe_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir(exist_ok=False)
    dump(out/'protocol.json',dict(diagnostic_only=True,seconds=60,reconnect=False,normalization=False,sqlite=False,source_DB_untouched=True,raw_receipt_preserved=True,script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()))
    dump(out/'clock_before.json',await asyncio.to_thread(clock_snapshot))
    markets=await asyncio.to_thread(PolymarketMarketDiscovery.get_active_btc_markets,verify_tls=True,raise_errors=True)
    selected=[next(m for m in markets if m['market_key']==d) for d in ('5m','15m')]
    results=await asyncio.gather(*(observe(m,out) for m in selected))
    dump(out/'clock_after.json',await asyncio.to_thread(clock_snapshot))
    dump(out/'manifest.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    print(str(out));print(json.dumps([{k:v for k,v in r.items() if k!='wire_age'}|{'quantiles_ms':r['wire_age']['quantiles_ms'],'max_ms':r['wire_age']['max_ms']} for r in results]))
if __name__=='__main__':asyncio.run(main())
