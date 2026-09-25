"""Public persistent WS book, strict identity/generation and source timestamps.
Independent of BTC V1 signal implementation. No REST snapshot-as-stream claim.
"""
import asyncio
import json
from contextlib import suppress
from .production_readonly import BookStateSource,number,now_ms

WS='wss://ws-subscriptions-clob.polymarket.com/ws/market'

class StreamBook(BookStateSource):
    def __init__(self,slug,condition,tokens,expiry,*,clock=now_ms):
        super().__init__(clock=clock)
        self.slug,self.condition,self.expected_tokens,self.expiry=slug,condition,tuple(tokens),expiry
        self.depth={};self.messages=0;self.failure=None
    def connected_generation(self):
        self.depth={}
        self.connect(self.slug,self.expected_tokens,(self.generation or 0)+1)
    def disconnect(self):
        super().disconnect();self.depth={}
    def ingest(self,event):
        try:
            if not self.connected or self.clock()>=self.expiry:raise ValueError('NOT_CONNECTED_OR_EXPIRED')
            if event.get('market')!=self.condition:raise ValueError('MARKET_IDENTITY')
            kind=event.get('event_type')
            if kind not in ('book','price_change'):
                if kind in ('last_trade_price','tick_size_change'):return
                raise ValueError('UNREVIEWED_MARKET_EVENT')
            stamp=int(event['timestamp'])
            if not 0<=self.clock()-stamp<=500:raise ValueError('STALE_WIRE_EVENT')
            touched=set()
            if kind=='book':
                token=event['asset_id']
                if token not in self.tokens:raise ValueError('TOKEN_IDENTITY')
                sides={}
                for side in ('bids','asks'):
                    rows=event[side]
                    if not isinstance(rows,list):raise ValueError('DEPTH_SCHEMA')
                    levels={}
                    for row in rows:
                        p,q=number(row['price']),number(row['size'])
                        if not 0<p<1 or q<=0 or p in levels:raise ValueError('DEPTH_LEVEL')
                        levels[p]=q
                    sides[side]=levels
                self.depth[token]=sides;touched.add(token)
            else:
                for change in event['price_changes']:
                    token=change['asset_id']
                    if token not in self.tokens:raise ValueError('TOKEN_IDENTITY')
                    if token not in self.depth:continue
                    side={'BUY':'bids','SELL':'asks'}[change['side']]
                    p,q=number(change['price']),number(change['size'])
                    if not 0<p<1 or q<0:raise ValueError('DELTA_LEVEL')
                    if q==0:self.depth[token][side].pop(p,None)
                    else:self.depth[token][side][p]=q
                    touched.add(token)
            for token in touched:
                b=self.depth[token]
                self.update(token,list(b['bids'].items()),list(b['asks'].items()),stamp,self.generation)
            self.messages+=1
        except Exception:
            self.disconnect();self.failure='WS_SCHEMA_IDENTITY_OR_FRESHNESS';raise ValueError(self.failure) from None
    def read(self):
        if self.clock()>=self.expiry:self.disconnect()
        return {**super().read(),'source':'PUBLIC_CLOB_PERSISTENT_WS','condition_verified':True,
                'messages_received':self.messages,'reason':self.failure}
    async def run(self):
        from websockets.asyncio.client import connect
        class FixedConnect(connect):
            def process_redirect(self,exc):return exc
        try:
            async with FixedConnect(WS,ping_interval=None,open_timeout=10,close_timeout=2,max_size=4000000) as ws:
                self.connected_generation()
                await ws.send(json.dumps({'assets_ids':list(self.tokens),'type':'market'}))
                async def heartbeat():
                    while True:
                        await asyncio.sleep(10)
                        try:await ws.send('PING')
                        except Exception:self.disconnect();return
                ping=asyncio.create_task(heartbeat())
                try:
                    while self.clock()<self.expiry:
                        raw=await asyncio.wait_for(ws.recv(),25)
                        if raw=='PONG':continue
                        values=json.loads(raw)
                        for event in values if isinstance(values,list) else [values]:self.ingest(event)
                finally:
                    ping.cancel()
                    with suppress(asyncio.CancelledError):await ping
        except asyncio.CancelledError:raise
        except Exception:self.failure='WS_DISCONNECTED_OR_INVALID'
        finally:self.disconnect()
