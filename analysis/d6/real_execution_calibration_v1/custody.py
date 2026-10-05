"""Custody is owned outside the trading task and verified independently.
The application must keep this owner/event loop alive; OS death needs an external
service. A local journal entry alone never proves transferred custody.
"""
import asyncio,copy,time,secrets
from .core import digest
from .schemas import identifiers,integer,hash256,text

class CustodyStateStore:
    """Independent fsynced journal of ownership; never a proof of remote acceptance."""
    def __init__(self,journal):self.journal=journal;self.states=self.recover_states(journal.path)
    @staticmethod
    def recover_states(path):
        from .core import Journal
        from pathlib import Path
        states={}
        if not Path(path).exists():
            return states
        for row in Journal.read(path):
            if row['kind']!='CUSTODY_STATE':raise ValueError('CUSTODY_STORE_SCHEMA')
            p=row['payload'];states[p['experiment_id']]=p['state']
        return states
    def record(self,experiment,state,details=None):
        self.journal.append("CUSTODY_STATE",dict(experiment_id=experiment,state=state,details=details or {}))
        self.states[experiment]=state

class ReceiptVerifier:
    def __init__(self,authority,owner,clock=lambda:time.time_ns()//1000000):
        self.authority=authority;self.owner=owner;self.clock=clock;self.seen=set()
    async def verify(self,receipt,request):
        if not isinstance(receipt,dict):return False
        rid=receipt.get('receipt_id');stamp=receipt.get('accepted_ms')
        if not rid or rid in self.seen or receipt.get('owner')!=self.owner:return False
        if type(stamp) is not int or not 0<=self.clock()-stamp<=5000:return False
        if any(receipt.get(k)!=request[k] for k in ('account','experiment_id','exposure_digest','journal_sequence')):return False
        try:
            text(rid);hash256(receipt['exposure_digest']);integer(receipt['journal_sequence'])
            identifiers(receipt.get('future_result_client_ids',[]))
        except (ValueError,KeyError):return False
        if await self.authority.verify_durable(copy.deepcopy(receipt)) is not True:return False
        self.seen.add(rid);return True

async def bounded(task,seconds):
    done,_=await asyncio.wait({task},timeout=seconds)
    if not done:return False
    task.result();return True

class CustodyOwner:
    def __init__(self,channel,verifier,*,timeout=1,state_store=None):
        self.state_store=state_store
        self.channel=channel;self.verifier=verifier;self.timeout=timeout
        self.tasks=set();self.errors=[];self.accepted={};self.states=dict(state_store.states) if state_store else {};self.operations=set();self.coordinators={};self.workers={};self.monitors={};self.requests={}
    def retain(self,c):
        key=c.ledger.journal.experiment_id
        if key in self.states:raise RuntimeError('CUSTODY_EXPERIMENT_ALREADY_OWNED_OR_RECORDED')
        self.states[key]='OWNED'
        self.persist(key,'OWNED',c.ledger.custody_snapshot())
        self.coordinators[key]=c
        return self.spawn(c)
    def spawn(self,c):
        key=c.ledger.journal.experiment_id
        task=asyncio.create_task(self._retain(c));self.tasks.add(task);self.workers[key]=task
        task.add_done_callback(self.tasks.discard)
        return task
    async def _retain(self,c):
        monitor=self.monitors.get(c.ledger.journal.experiment_id);pending=None
        try:
            while True:
                if monitor is None or monitor.done():
                    if monitor is not None:
                        try:monitor.result()
                        except BaseException as e:self.errors.append(type(e).__name__)
                    monitor=asyncio.create_task(c.monitor_account());self.monitors[c.ledger.journal.experiment_id]=monitor
                if self.operations:
                    await asyncio.wait(set(self.operations),timeout=.1);continue
                l=c.ledger
                observed=l.custody_snapshot();key=l.journal.experiment_id
                previous=self.requests.get(key)
                # Retain the actual request's journal checkpoint while only monitor
                # events change. New exposure always creates a new challenge.
                expired=previous is not None and getattr(self.channel,'request_expired',lambda r:False)(previous)
                if expired:observed['custody_request_nonce']=secrets.token_hex(16)
                if previous is None or expired or previous['exposure_revision']!=observed['exposure_revision']:self.requests[key]=observed
                request=copy.deepcopy(self.requests[key])
                try:
                    pending=asyncio.create_task(self.channel.accept(copy.deepcopy(request)));self.operations.add(pending)
                    pending.add_done_callback(self.operations.discard)
                    if not await bounded(pending,self.timeout):
                        pending.cancel();self.errors.append('HANDOFF_TIMEOUT')
                        # Do not spawn unlimited retries when a channel ignores cancellation.
                        while not pending.done():
                            if monitor.done():
                                try:monitor.result()
                                except BaseException as e:self.errors.append(type(e).__name__)
                                monitor=asyncio.create_task(c.monitor_account());self.monitors[c.ledger.journal.experiment_id]=monitor
                            await asyncio.sleep(.1)
                        continue
                    receipt=pending.result()
                    validation=asyncio.create_task(self.verifier.verify(receipt,request));self.operations.add(validation)
                    validation.add_done_callback(self.operations.discard)
                    if await bounded(validation,self.timeout) and validation.result():
                        # No await between revision recheck and ownership transition.
                        if l.custody_snapshot()['exposure_revision']!=request['exposure_revision']:
                            self.errors.append('STALE_EXPOSURE_RECEIPT');await asyncio.sleep(.1);continue
                        future=set(receipt.get('future_result_client_ids',[]))
                        unknown=set(l.orders)  # include terminal intents: late corrections also need custody
                        active_pending=[t for t in c.v1['pending'] if not t.done()]
                        if (c.busy or active_pending or unknown) and not unknown<=future:
                            self.errors.append('FUTURE_RESULTS_NOT_ACCEPTED');await asyncio.sleep(.1);continue
                        if c.busy or active_pending:
                            self.errors.append('STRATEGY_STILL_PENDING');await asyncio.sleep(.1);continue
                        self.accepted[l.journal.experiment_id]=receipt
                        if not self.persist(l.journal.experiment_id,'TRANSFERRED',receipt):
                            self.accepted.pop(l.journal.experiment_id,None);await asyncio.sleep(.1);continue
                        self.states[l.journal.experiment_id]='TRANSFERRED'
                        try:l.emit('EXPOSURE_CUSTODY_HANDOFF',receipt)
                        except Exception as e:self.errors.append(type(e).__name__)
                        return receipt
                    validation.cancel()
                    while not validation.done():
                        if monitor.done():
                            try:monitor.result()
                            except BaseException as e:self.errors.append(type(e).__name__)
                            monitor=asyncio.create_task(c.monitor_account());self.monitors[c.ledger.journal.experiment_id]=monitor
                        await asyncio.sleep(.1)
                except asyncio.CancelledError:
                    # Trading task cancellation must not be forwarded here; an explicit
                    # external process owner remains required for application shutdown.
                    raise
                except Exception as e:self.errors.append(type(e).__name__)
                await asyncio.sleep(.1)
        finally:
            key=c.ledger.journal.experiment_id
            if self.states.get(key)!='TRANSFERRED':
                self.states[key]='UNRESOLVED_FAILURE';self.persist(key,'UNRESOLVED_FAILURE')
            if monitor is not None and self.states.get(key)=='TRANSFERRED':
                if monitor.done():
                    try:monitor.result()
                    except BaseException:pass
                else:monitor.cancel()
            if pending is not None and not pending.done():pending.cancel()

    def persist(self,key,state,details=None):
        if self.state_store is None:return True  # fixture-only; live root requires a store
        try:self.state_store.record(key,state,details);return True
        except Exception as exc:self.errors.append('CUSTODY_STATE_STORAGE:'+type(exc).__name__);return False

    async def shutdown_flat(self):
        if self.tasks or self.operations or any(v!='TRANSFERRED' for v in self.states.values()):raise RuntimeError('CUSTODY_STILL_OWNED')

    async def wait_resolved(self):
        # Application root must await this before returning to asyncio.run shutdown.
        cancellation=None
        while self.tasks or self.operations or any(v!='TRANSFERRED' for v in self.states.values()):
            for key,c in self.coordinators.items():
                worker=self.workers[key]
                if self.states[key]!='TRANSFERRED' and worker.done():
                    try:worker.result()
                    except BaseException as exc:self.errors.append('OWNER_RECLAIM:'+type(exc).__name__)
                    self.states[key]='OWNED';self.persist(key,'OWNED',c.ledger.custody_snapshot());self.spawn(c)
            try:
                active=set(self.tasks)|set(self.operations)
                if active:await asyncio.wait(active,timeout=.1)
                else:await asyncio.sleep(.1)
            except asyncio.CancelledError as exc:cancellation=exc
            try:await asyncio.sleep(.1)
            except asyncio.CancelledError as exc:cancellation=exc
        await self.shutdown_flat()
        if cancellation is not None:raise cancellation
