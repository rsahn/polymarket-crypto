"""Public persistent WS book, strict identity/generation and source timestamps.
Independent of BTC V1 signal implementation. No REST snapshot-as-stream claim.
"""
import asyncio
import json
import copy
import hashlib
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
            'resync_complete_generation':None,'regression_event':None,'transitions':[],'tokens':[]}
        self.first_full_books={};self.events_seen=0;self.snapshot_refs={}
        self.last_books={};self.last_wire_event_ms=None;self.last_valid_book_ms=None;self.attempted_books={}
    def transition(self,kind):
        self.diagnostics['transitions'].append({'kind':kind,'generation':self.generation,'at_ms':self.clock(),'reason':self.failure})
        self.diagnostics['transitions']=self.diagnostics['transitions'][-32:]
    def connected_generation(self):
        self.depth={}
        self.connect(self.slug,self.expected_tokens,(self.generation or 0)+1)
        self.failure=None;self.last_books={};self.attempted_books={};self.last_valid_book_ms=None;self.last_wire_event_ms=None
        self.diagnostics['resync_complete_generation']=None
        self.diagnostics['regression_event']=None
        self.first_full_books={};self.events_seen=0;self.snapshot_refs={}
        self.transition('CONNECTED_AWAITING_TWO_FULL_BOOKS')
    def disconnect(self):
        if self.connected:self.transition('DISCONNECTED')
        super().disconnect();self.depth={}
    def capture_first_book(self,event):
        if not isinstance(event,dict) or event.get('event_type')!='book':return
        token=event.get('asset_id')
        if token not in self.expected_tokens or token in self.first_full_books:return
        try:
            bids,asks=event['bids'],event['asks']
            if not isinstance(bids,list) or not isinstance(asks,list):return
            bid=[number(x['price']) for x in bids];ask=[number(x['price']) for x in asks]
            self.first_full_books[token]={'token_index':self.expected_tokens.index(token),
                'token_sha256':hashlib.sha256(token.encode()).hexdigest(),
                'identity_matches':event.get('market')==self.condition,'message_kind':'book',
                'bids_count':len(bids),'asks_count':len(asks),'best_bid':str(max(bid)) if bid else None,
                'best_ask':str(min(ask)) if ask else None,'source_timestamp_ms':int(event['timestamp']),
                'generation':self.generation}
        except (KeyError,TypeError,ValueError):return
    def reject_regression_before_mutation(self,token,stamp,kind,received_ms):
        previous=self.books.get(token)
        if previous is None or stamp>=previous['observed_ms']:return
        ref=self.snapshot_refs.get(token,{})
        count=ref.get('accepted_deltas',0)
        classification=('FULL_BOOK_REGRESSION' if kind=='book' else
            'REGRESSION_AFTER_ACCEPTED_DELTA' if count else
            'PRE_SNAPSHOT_DELTA_SUPERSESSION_UNPROVEN' if ref.get('generation')==self.generation
                and stamp<ref.get('source_ms',-1) else 'TEMPORAL_REGRESSION_UNPROVEN')
        self.diagnostics['regression_event']={
            'event_type':kind,'token_index':self.expected_tokens.index(token),
            'token_sha256':hashlib.sha256(token.encode()).hexdigest(),
            'source_timestamp_ms':stamp,'previous_accepted_source_timestamp_ms':previous['observed_ms'],
            'received_timestamp_ms':received_ms,'delta_ms':stamp-previous['observed_ms'],
            'generation':self.generation,'reason':'BOOK_REGRESSION',
            'comparison':'source_timestamp_ms < same_token_accepted_source_timestamp_ms',
            'watermark_scope':'TOKEN_WITHIN_CONNECTION_GENERATION',
            'reference_full_book_ms':ref.get('source_ms'),'accepted_deltas_since_full_book':count,
            'classification':classification,'supersession_proven':False}
        raise ValueError('BOOK_REGRESSION')

    def ingest(self,event):
        received_ms=self.clock()
        self.events_seen+=1
        self.capture_first_book(event)
        try:
            if not self.connected or self.clock()>=self.expiry:raise ValueError('NOT_CONNECTED_OR_EXPIRED')
            if event.get('market')!=self.condition:raise ValueError('MARKET_IDENTITY')
            kind=event.get('event_type')
            if kind not in ('book','price_change'):
                if kind in ('last_trade_price','tick_size_change'):return
                raise ValueError('UNREVIEWED_MARKET_EVENT')
            raw_stamp=event['timestamp']
            if not (type(raw_stamp) is int or isinstance(raw_stamp,str) and raw_stamp.isascii() and raw_stamp.isdigit()):
                raise ValueError('AMBIGUOUS_TIMESTAMP')
            stamp=int(raw_stamp);self.last_wire_event_ms=stamp
            if not 0<=self.clock()-stamp<=500:raise ValueError('STALE_WIRE_EVENT')
            # Check every affected token before any depth mutation (including
            # a multi-token delta). Timestamp order alone is not supersession proof.
            candidates=[event['asset_id']] if kind=='book' else [c['asset_id'] for c in event['price_changes']]
            for candidate in candidates:
                if candidate not in self.tokens:raise ValueError('TOKEN_IDENTITY')
                self.reject_regression_before_mutation(candidate,stamp,kind,received_ms)
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
            for token in sorted(touched,key=self.expected_tokens.index):
                b=self.depth[token]
                self.attempted_books[token]={'bids_count':len(b['bids']),'asks_count':len(b['asks']),
                    'best_bid':str(max(b['bids'])) if b['bids'] else None,
                    'best_ask':str(min(b['asks'])) if b['asks'] else None,'generation':self.generation}
                # update clears both books on failure. Preserve the accepted per-token
                # watermark BEFORE calling it; never retain raw wire payloads or IDs.
                previous=self.books.get(token)
                previous_stamp=previous['observed_ms'] if previous else None
                try:
                    self.update(token,list(b['bids'].items()),list(b['asks'].items()),stamp,self.generation)
                except ValueError as exc:
                    if exc.args==('BOOK_REGRESSION',):
                        self.diagnostics['regression_event']={
                            'event_type':kind,'token_index':self.expected_tokens.index(token),
                            'token_sha256':hashlib.sha256(token.encode()).hexdigest(),
                            'source_timestamp_ms':stamp,'previous_accepted_source_timestamp_ms':previous_stamp,
                            'received_timestamp_ms':received_ms,'delta_ms':stamp-previous_stamp,
                            'generation':self.generation,'reason':'BOOK_REGRESSION',
                            'comparison':'source_timestamp_ms < same_token_accepted_source_timestamp_ms',
                            'watermark_scope':'TOKEN_WITHIN_CONNECTION_GENERATION'}
                    raise
            for token in touched:
                if kind=='book':self.snapshot_refs[token]={'source_ms':stamp,'generation':self.generation,'accepted_deltas':0}
                elif token in self.snapshot_refs:self.snapshot_refs[token]['accepted_deltas']+=1
            self.messages+=1
            if touched:self.last_valid_book_ms=stamp
            for token in touched:
                self.last_books[token]={'last_valid_book_ms':stamp,'bids_present':bool(self.depth[token]['bids']),
                                        'asks_present':bool(self.depth[token]['asks']),'generation':self.generation}
            self.diagnostics['last_valid_message']={'kind':kind,'source_ms':stamp,'received_ms':self.clock(),'generation':self.generation}
            if super().read()['book_synced'] and self.diagnostics['resync_complete_generation']!=self.generation:
                self.diagnostics['resync_complete_generation']=self.generation;self.failure=None;self.transition('RESYNC_COMPLETE')
        except Exception as exc:
            reasons={'NOT_CONNECTED_OR_EXPIRED','MARKET_IDENTITY','UNREVIEWED_MARKET_EVENT','STALE_WIRE_EVENT',
                     'TOKEN_IDENTITY','DEPTH_SCHEMA','DEPTH_LEVEL','DELTA_LEVEL','STALE_BOOK','EMPTY_BOOK','CROSSED_BOOK',
                     'BOOK_REGRESSION','INVALID_DEPTH','DUPLICATE_PRICE','AMBIGUOUS_TIMESTAMP'}
            reason=exc.args[0] if exc.args and isinstance(exc.args[0],str) and exc.args[0] in reasons else 'BOOK_SCHEMA_OR_DEPTH_INVALID'
            self.diagnostics['parser_reason']=reason
            self.diagnostics['rejected_message_age_ms']=self.clock()-stamp if 'stamp' in locals() else None
            self.failure=reason
            # A local rejection is not a TCP disconnect. Invalidate both tokens;
            # only two new full snapshots may establish a usable book again.
            self.books={};self.depth={};self.snapshot_refs={};self.diagnostics['resync_complete_generation']=None
            self.transition('INVALIDATED_AWAITING_TWO_FULL_BOOKS')
            raise ValueError(reason) from None
    def read(self):
        if self.clock()>=self.expiry:
            self.failure=self.failure or 'MARKET_EXPIRED';self.disconnect()
        base=super().read()
        state=('DISCONNECTED' if not self.connected else
               'STALE' if self.failure in ('STALE_WIRE_EVENT','STALE_BOOK') or (base['synchronized'] and not base['fresh']) else
               'INVALID_BOOK' if self.failure else 'SYNCHRONIZED' if base['available'] else
               'CONNECTED' if not self.events_seen else 'INITIAL_SNAPSHOT_PENDING')
        d=copy.deepcopy(self.diagnostics)
        d['first_full_books']=copy.deepcopy(list(self.first_full_books.values()))
        d['tokens']=[{'token_index':i,**self.last_books.get(t,{}),**self.attempted_books.get(t,{}),
            'last_valid_book_age_ms':self.clock()-self.last_books[t]['last_valid_book_ms'] if t in self.last_books else None,
            'current_generation_synced':self.connected and t in self.depth and t in self.books}
            for i,t in enumerate(self.expected_tokens)]
        return {**base,'state':state,'diagnostics':d,'source':'PUBLIC_CLOB_PERSISTENT_WS','condition_verified':True,
                'messages_received':self.messages,'reason':self.failure or super().read()['reason'],
                'last_wire_event_ms':self.last_wire_event_ms,'last_valid_book_ms':self.last_valid_book_ms}
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
                        for event in values if isinstance(values,list) else [values]:
                            try:self.ingest(event)
                            except ValueError:
                                if self.failure not in {'EMPTY_BOOK','CROSSED_BOOK','STALE_WIRE_EVENT'}:raise
                                # Remain connected but unusable pending full resync.
                                continue
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
