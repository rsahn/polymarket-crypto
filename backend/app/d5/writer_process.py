"""Experimental bounded async transport; not wired into the live collector.

Only trusted local command bytes enter pickle. No network pickle is accepted.
Admission failure is explicit; callers must stop ingress and preserve failure.
"""
import asyncio
from collections import deque
import multiprocessing as mp
import pickle
import queue
import time
import traceback
from .writer_core import WriterCore


def _worker(inbox, replies, path, config):
    core = None
    try:
        core = WriterCore(path, config=config)
        replies.put({'type':'READY','session_id':core.store.session_id})
        while True:
            batch = inbox.get()
            ack = None
            for index,data in enumerate(batch):
                command = pickle.loads(data)
                ack = core.apply(command)
                if ack['closed'] and index != len(batch)-1:
                    raise RuntimeError('COMMAND_AFTER_STOP')
            replies.put({'type':'ACK',**ack})
            if core.closed:
                return
    except BaseException as exc:
        if core is not None and not core.closed:
            try:
                core.fail(exc)
            except BaseException:
                pass
        replies.put({'type':'ERROR','error':str(exc),'traceback':traceback.format_exc()})
        raise


class ProcessWriter:
    def __init__(self, path, *, max_items=256, max_bytes=8*1024*1024,
                 batch_size=32, flush_seconds=.005, config=None):
        if min(max_items,max_bytes,batch_size) <= 0 or flush_seconds <= 0:
            raise ValueError('Positive bounds required')
        self.path = str(path)
        self.config = dict(config or {})
        self.max_items,self.max_bytes = max_items,max_bytes
        self.batch_size,self.flush_seconds = batch_size,flush_seconds
        context = mp.get_context('spawn')
        self.inbox = context.Queue(maxsize=8)
        self.replies = context.Queue(maxsize=8)
        self.process = context.Process(target=_worker,args=(self.inbox,self.replies,self.path,self.config))
        self.pending = deque()
        self.outstanding = deque()
        self.outstanding_bytes = 0
        self.high_water_items = self.high_water_bytes = 0
        self.last_sent_sequence = -1
        self.next_sequence = 0
        self.processed_sequence = self.committed_sequence = -1
        self.error = None
        self.session_id = None
        self.stop_sequence = None
        self.closed_ack = False
        self.started = False
        self.wake = asyncio.Event()
        self.pump_task = None
        self.last_ack = None

    async def start(self):
        if self.started:raise RuntimeError('Writer already started')
        self.started = True
        self.process.start()
        self.pump_task = asyncio.create_task(self._pump())
        while self.session_id is None:
            self._check()
            await asyncio.sleep(.005)
        return self.session_id

    def _check(self):
        if self.error is not None:raise RuntimeError('WRITER_FAILED: '+self.error)
        if not self.started:raise RuntimeError('Writer not started')

    def submit(self, command):
        self._check()
        if self.stop_sequence is not None:raise RuntimeError('Writer stopping')
        command = dict(command)
        command['sequence'] = self.next_sequence
        data = pickle.dumps(command,protocol=5)  # freeze before returning to caller
        is_stop = command['kind'] == 'STOP'
        # One small stop control is reserved so a full queue can still drain.
        if is_stop and len(data)>4096:raise ValueError('Oversized stop control')
        if not is_stop and (len(self.outstanding)>=self.max_items or
                            self.outstanding_bytes+len(data)>self.max_bytes):
            raise BufferError('WRITER_CAPACITY_EXCEEDED: command not accepted')
        sequence = self.next_sequence
        self.next_sequence += 1
        self.pending.append((data,command['kind'],time.monotonic()))
        self.outstanding.append((sequence,len(data),time.monotonic()))
        self.outstanding_bytes += len(data)
        self.high_water_items = max(self.high_water_items,len(self.outstanding))
        self.high_water_bytes = max(self.high_water_bytes,self.outstanding_bytes)
        if is_stop:self.stop_sequence=sequence
        self.wake.set()
        return sequence

    def _reap(self):
        while True:
            try:reply=self.replies.get_nowait()
            except queue.Empty:return
            if reply['type']=='ERROR':
                self.error=reply['error'];return
            if reply['type']=='READY':
                self.session_id=reply['session_id'];continue
            seq=reply['sequence']
            if not self.processed_sequence < seq <= self.last_sent_sequence:
                self.error='ACK_SEQUENCE_MISMATCH';return
            committed=reply['committed_sequence']
            if not self.committed_sequence <= committed <= seq:
                self.error='ACK_COMMIT_SEQUENCE_MISMATCH';return
            if reply['closed'] and (seq!=self.stop_sequence or committed!=seq):
                self.error='UNCLEAN_STOP_ACK';return
            self.processed_sequence=seq
            self.committed_sequence=committed
            while self.outstanding and self.outstanding[0][0]<=seq:
                _,size,_=self.outstanding.popleft();self.outstanding_bytes-=size
            self.last_ack=reply
            self.closed_ack=reply['closed']

    async def _pump(self):
        try:
            while True:
                self._reap()
                if self.error is not None:return
                if self.closed_ack:
                    if self.pending or self.outstanding:
                        self.error='UNEXPECTED_PENDING_AFTER_STOP'
                    return
                if self.process.exitcode is not None:
                    # Queue feeder final messages may become visible after exit detection.
                    await asyncio.sleep(.02);self._reap()
                    if not self.closed_ack and self.error is None:
                        self.error='PROCESS_EXIT_WITHOUT_CLEAN_ACK: '+str(self.process.exitcode)
                    return
                if self.pending:
                    barrier=any(kind not in ('BOOK','BTC') for _,kind,_ in self.pending)
                    due=time.monotonic()-self.pending[0][2]>=self.flush_seconds
                    if barrier or due or len(self.pending)>=self.batch_size:
                        n=min(self.batch_size,len(self.pending))
                        batch=[self.pending[i][0] for i in range(n)]
                        try:self.inbox.put_nowait(batch)
                        except queue.Full:pass
                        else:
                            self.last_sent_sequence += n
                            for _ in range(n):self.pending.popleft()
                self.wake.clear()
                try:await asyncio.wait_for(self.wake.wait(),timeout=min(self.flush_seconds,.01))
                except asyncio.TimeoutError:pass
        except Exception as exc:
            self.error='TRANSPORT_ERROR: '+str(exc)

    def stats(self):
        return {'submitted':self.next_sequence,'sent_sequence':self.last_sent_sequence,
                'processed_sequence':self.processed_sequence,'committed_sequence':self.committed_sequence,
                'outstanding_items':len(self.outstanding),'outstanding_bytes':self.outstanding_bytes,
                'high_water_items':self.high_water_items,'high_water_bytes':self.high_water_bytes,
                'oldest_unacknowledged_age_seconds':time.monotonic()-self.outstanding[0][2] if self.outstanding else 0.,
                'pending_batches_items':len(self.pending),'worker_pid':self.process.pid,
                'closed_ack':self.closed_ack,'error':self.error}

    async def wait_processed(self, sequence):
        while self.processed_sequence<sequence:
            self._check();await asyncio.sleep(.005)
        self._check()
        return self.last_ack

    async def stop(self, *, received_ts_ms=None, status='STOPPED', payload=None, cleanup_errors=None,
                   collection_stop_already_recorded=False):
        if self.stop_sequence is None:
            self.submit({'kind':'STOP','received_ts_ms':received_ts_ms or time.time_ns()//1_000_000,
                         'status':status,'payload':dict(payload or {}),'cleanup_errors':list(cleanup_errors or []),
                         'collection_stop_already_recorded':collection_stop_already_recorded})
        await self.wait_processed(self.stop_sequence)
        while self.process.is_alive():await asyncio.sleep(.005)
        self.process.join()
        if self.process.exitcode!=0:raise RuntimeError('Writer exit failure')
        await self.pump_task
        self._check()
        self.inbox.close();self.inbox.join_thread()
        self.replies.close();self.replies.join_thread()
        return self.last_ack

    async def release_failed(self):
        """Release handles only after a failed child exits; never terminate it."""
        while self.process.is_alive():await asyncio.sleep(.005)
        self.process.join()
        if self.pump_task is not None:await self.pump_task
        self.inbox.cancel_join_thread();self.inbox.close()
        self.replies.close();self.replies.join_thread()
