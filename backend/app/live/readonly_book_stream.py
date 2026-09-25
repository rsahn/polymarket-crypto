"""Public persistent WS book, strict identity/generation and source timestamps.
Independent of BTC V1 signal implementation. No REST snapshot-as-stream claim.
"""
import asyncio
import json
import copy
from contextlib import suppress
from .production_readonly import BookStateSource,number,now_ms

WS='wss://ws-subscriptions-clob.polymarket.com/ws/market'

class StreamBook(BookStateSource):
    def __init__(self,slug,condition,tokens,expiry,*,clock=now_ms):
        super().__init__(clock=clock)
        self.slug,self.condition,self.expected_tokens,self.expiry=slug,condition,tuple(tokens),expiry
        self.depth={};self.messages=0;self.failure=None
        self.diagnostics={'parser_reason':None,'exception_category':None,'close_code':None,
            'close_reason_category':None,'remote_close_reason_present':False,'last_valid_message':None,
            'resync_complete_generation':None,'transitions':[],'tokens':[]}
        self.last_books={}
    def transition(self,kind):
        self.diagnostics['transitions'].append({'kind':kind,'generation':self.generation,'at_ms':self.clock()})
        self.diagnostics['transitions']=self.diagnostics['transitions'][-32:]
    def connected_generation(self):
        self.depth={}
        self.connect(self.slug,self.expected_tokens,(self.generation or 0)+1)
        self.failure=None;self.last_books={}
        self.diagnostics['resync_complete_generation']=None
        self.transition('CONNECTED_AWAITING_TWO_FULL_BOOKS')
    def disconnect(self):
        if self.connected:self.transition('DISCONNECTED')
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
            for token in touched:
                self.last_books[token]={'last_valid_book_ms':stamp,'bids_present':bool(self.depth[token]['bids']),
                                        'asks_present':bool(self.depth[token]['asks']),'generation':self.generation}
            self.diagnostics['last_valid_message']={'kind':kind,'source_ms':stamp,'received_ms':self.clock(),'generation':self.generation}
            if super().read()['book_synced'] and self.diagnostics['resync_complete_generation']!=self.generation:
                self.diagnostics['resync_complete_generation']=self.generation;self.transition('RESYNC_COMPLETE')
        except Exception as exc:
            reasons={'NOT_CONNECTED_OR_EXPIRED','MARKET_IDENTITY','UNREVIEWED_MARKET_EVENT','STALE_WIRE_EVENT',
                     'TOKEN_IDENTITY','DEPTH_SCHEMA','DEPTH_LEVEL','DELTA_LEVEL','STALE_BOOK','EMPTY_OR_CROSSED_BOOK',
                     'BOOK_REGRESSION','INVALID_DEPTH','DUPLICATE_PRICE'}
            reason=exc.args[0] if exc.args and isinstance(exc.args[0],str) and exc.args[0] in reasons else 'BOOK_SCHEMA_OR_DEPTH_INVALID'
            self.diagnostics['parser_reason']=reason
            self.diagnostics['rejected_message_age_ms']=self.clock()-stamp if 'stamp' in locals() else None
            self.failure=reason;self.disconnect();raise ValueError(reason) from None
    def read(self):
        if self.clock()>=self.expiry:
            self.failure=self.failure or 'MARKET_EXPIRED';self.disconnect()
        d=copy.deepcopy(self.diagnostics)
        d['tokens']=[{'token_index':i,**self.last_books.get(t,{}),
            'last_valid_book_age_ms':self.clock()-self.last_books[t]['last_valid_book_ms'] if t in self.last_books else None,
            'current_generation_synced':self.connected and t in self.depth and t in self.books}
            for i,t in enumerate(self.expected_tokens)]
        return {**super().read(),'diagnostics':d,'source':'PUBLIC_CLOB_PERSISTENT_WS','condition_verified':True,
                'messages_received':self.messages,'reason':self.failure}
    async def run(self,*,connect_factory=None):
        from websockets.asyncio.client import connect
        class FixedConnect(connect):
            def process_redirect(self,exc):return exc
        try:
            async with (connect_factory or FixedConnect)(WS,ping_interval=None,open_timeout=10,close_timeout=2,max_size=4000000) as ws:
                self.connected_generation()
                await ws.send(json.dumps({'assets_ids':list(self.tokens),'type':'market'}))
                async def heartbeat():
                    while True:
                        await asyncio.sleep(10)
                        try:await ws.send('PING')
                        except Exception:
                            self.failure='WS_HEARTBEAT_FAILED';self.disconnect();return
                ping=asyncio.create_task(heartbeat())
                try:
                    while self.clock()<self.expiry:
                        raw=await asyncio.wait_for(ws.recv(),25)
                        if raw=='PONG':continue
                        try:values=json.loads(raw)
                        except (ValueError,TypeError):
                            self.diagnostics['parser_reason']='WS_INVALID_JSON';self.failure='WS_INVALID_JSON'
                            raise ValueError('WS_INVALID_JSON') from None
                        for event in values if isinstance(values,list) else [values]:self.ingest(event)
                finally:
                    ping.cancel()
                    with suppress(asyncio.CancelledError):await ping
        except asyncio.CancelledError:
            self.transition('LOCAL_TASK_CANCELLED');raise
        except Exception as exc:
            from websockets.exceptions import ConnectionClosed
            if isinstance(exc,ConnectionClosed):
                received=exc.rcvd
                self.diagnostics['close_code']=received.code if received else None
                self.diagnostics['remote_close_reason_present']=bool(received and received.reason)
                self.diagnostics['close_reason_category']='REMOTE_CLOSE_FRAME' if received else 'NO_CLOSE_FRAME'
                category='CONNECTION_CLOSED'
            elif isinstance(exc,TimeoutError):category='RECEIVE_OR_CONNECT_TIMEOUT'
            elif isinstance(exc,OSError):category='NETWORK_OS_ERROR'
            else:category='PARSER_OR_PROTOCOL_ERROR'
            self.diagnostics['exception_category']=category
            self.failure=self.failure or category
        else:
            self.failure=self.failure or 'MARKET_EXPIRED'
        finally:self.disconnect()
