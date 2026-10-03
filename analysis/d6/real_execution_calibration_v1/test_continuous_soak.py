"""Single supervisor/ledger/arm/journal, 72h logical wall clock. No real network."""
import asyncio,heapq,itertools,json,time,os
from pathlib import Path
from .test_runtime_qualification import fixture,drive
from .core import Journal
from .supervisor import run
from .adapters import BookAdapter
from .custody import CustodyOwner,ReceiptVerifier
from .test_repairs import Authority
from .capacity import QUOTA_BYTES,MAX_RECORD_BYTES,PROJECTED_BYTES
from app.live.readonly_book_stream import StreamBook

class VirtualTime:
    def __init__(self,now):self.now=now;self.queue=[];self.ids=itertools.count()
    async def sleep(self,seconds):
        f=asyncio.get_running_loop().create_future()
        heapq.heappush(self.queue,(self.now[0]+round(seconds*1000),next(self.ids),f))
        await f
    async def supervise_sleep(self,seconds):await self.sleep(max(1,seconds))
    async def drive(self,task):
        while not task.done():
            # Drain ordinary ready callbacks before advancing simulated time.
            turns=0
            while asyncio.get_running_loop()._ready:
                await asyncio.sleep(0);turns+=1
                if turns>1000:raise AssertionError('runnable task did not yield')
            while self.queue and self.queue[0][2].done():heapq.heappop(self.queue)
            if not self.queue:
                if task.done():break
                raise AssertionError('virtual scheduler deadlock')
            self.now[0]=max(self.now[0],self.queue[0][0])
            while self.queue and self.queue[0][0]<=self.now[0]:
                _,_,f=heapq.heappop(self.queue)
                if not f.done():f.set_result(None)
        return await task

def test_continuous_72h_single_supervisor(tmp_path,monkeypatch):
    # Logical-time test only: coalesce physical barriers, not journal records.
    # Production fsync and crash semantics are exercised by the durability suites.
    real_fsync=os.fsync;barriers=[0]
    def barrier(fd):
        barriers[0]+=1
        if barriers[0]%1024==0:real_fsync(fd)
    monkeypatch.setattr(os,'fsync',barrier)
    async def case():
        c,l,now,log,calls=fixture(tmp_path,logged=False,token='1',down='2')
        class Quiet:
            def write(self,*a):pass
            def flush(self):pass

        l.journal.max_bytes=QUOTA_BYTES;l.journal.max_record_bytes=MAX_RECORD_BYTES
        # Accelerated storage boundary: preserve every byte/record, flush at end.
        # Raw production writes/fsync are separately exercised without this fixture.
        l.journal.file.close();l.journal.file=l.journal.path.open('ab',buffering=1024**2)
        original_submit=c.port.submit_once
        async def submit(cid,order):
            l.journal.file.flush();real_fsync(l.journal.file.fileno())
            return await original_submit(cid,order)
        c.port.submit_once=submit
        vt=VirtualTime(now);start=now[0];c.sleep=vt.sleep;c.arm.started_monotonic=start/1000

        stream=StreamBook('initial','m',('1','2'),now[0]+301000,clock=lambda:now[0])
        book=BookAdapter(stream,market='m',tokens={'UP':'1','DOWN':'2'},clock=lambda:now[0]);c.book_source=book
        counts=dict(rotations=0,reconnects=0,btc_reconnects=0,btc_ticks=0,account_failures=0,account_reads=0)
        original=c.account_source.snapshot
        async def snapshot():
            counts['account_reads']+=1
            if counts['account_reads']%300==0 and not c.busy:
                counts['account_failures']+=1;raise TimeoutError('synthetic availability')
            return await original()
        c.account_source.snapshot=snapshot
        def seed():
            for token in book.tokens.values():
                book.stream.ingest(dict(event_type='book',market=book.market,asset_id=token,timestamp=now[0],bids=[dict(price='.49',size='100')],asks=[dict(price='.5',size='100')]))
            assert book.stream.read()['available']
        class Books:
            async def run(self,status):
                book.stream.connected_generation();seed()
                next_rotation=start+300000
                while True:
                    if now[0]>=next_rotation:
                        status('WS_DISCONNECT');counts['rotations']+=1
                        n=counts['rotations']
                        await book.rotate('market-'+str(n),'m'+str(n),(str(2*n+1),str(2*n+2)),now[0]+301000)
                        book.stream.disconnect();counts['reconnects']+=1
                        book.stream.connected_generation()
                        next_rotation+=300000
                    seed();await vt.sleep(.5)
        class Signals:
            async def run(self,tick,status):
                from types import SimpleNamespace
                async def emit(price):
                    await tick(SimpleNamespace(price=price,event_ts_ms=now[0]-1,recv_ts_ms=now[0]));counts['btc_ticks']+=1
                # Three actual V1 entries/exits on successive markets. No cap reset.
                await vt.sleep(.1)
                for price in (100,100.1):
                    await emit(price);await vt.sleep(.1)
                next_tick=start+1000
                while True:
                    await vt.sleep((next_tick-now[0])/1000)
                    reconnect=(next_tick-start)%300000==0
                    if reconnect:
                        status('BTC_RECONNECT');counts['btc_reconnects']+=1
                    await emit(100)
                    if reconnect and counts['btc_reconnects']<=2:
                        while l.stop_new_entries:await vt.sleep(.1)
                        await emit(100);await vt.sleep(.1);await emit(100.1)
                    next_tick=start+((now[0]-start)//1000+1)*1000
        authority=Authority()
        class Channel:
            async def accept(self,request):return authority.seal(dict(**request,owner='owner',receipt_id='fixture',accepted_ms=now[0]))
        owner=CustodyOwner(Channel(),ReceiptVerifier(authority,'owner',clock=lambda:now[0]))
        started=time.monotonic()
        task=asyncio.create_task(run(c,Signals(),Books(),tmp_path/'reports',owner,clock=lambda:now[0]/1000,sleep=vt.supervise_sleep))
        try:
            result=await vt.drive(task)
            assert result['runtime_seconds']==259200
            assert l.reconciled and l.active is None and not any(l.positions.values())
            assert l.attempts==3 and len(l.orders)==6 and len(l.fills)==6 and l.allocated==78
            assert counts['rotations']==863 and counts['reconnects']==863 and counts['btc_reconnects']==863
            assert counts['btc_ticks']>=259190 and c.v1['diagnostics']()['V1_SIGNALS']==3
            assert counts['account_reads']>=259200 and counts['account_failures']>=864
            l.journal.file.flush();real_fsync(l.journal.file.fileno())
            total=0;kinds={};maximum=0
            for row in Journal.read(l.journal.path):
                total+=1;kinds[row['kind']]=kinds.get(row['kind'],0)+1
            with l.journal.path.open('rb') as f:
                for line in f:maximum=max(maximum,len(line))
            assert kinds['RECOVERY_COMPLETE']>=864 and maximum<=MAX_RECORD_BYTES
            assert l.journal.bytes<PROJECTED_BYTES
            # Auditable metrics retained by pytest output in the suite artifact.
            print('CONTINUOUS_SOAK='+json.dumps(dict(**counts,logical_seconds=result['runtime_seconds'],sessions=1,journal_rows=total,journal_bytes=l.journal.bytes,log_capacity_model_bytes=PROJECTED_BYTES,max_record_bytes=maximum,quota_bytes=QUOTA_BYTES,real_seconds=time.monotonic()-started,fsync_mode='test-only buffered IO/coalesced barriers; production unchanged')))
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
            l.journal.file.flush();real_fsync(l.journal.file.fileno())
            l.journal.close()
    asyncio.run(case())
