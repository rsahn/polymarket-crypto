"""Trading supervision; independent injected custody owner outlives this task."""
import asyncio,time
from .reports import Reports
from .custody import CustodyOwner
from .engine import transient_availability

TARGET_RUNTIME_SECONDS=259200

def stop_memory(c,reason):
    c.ledger.stop=True;c.ledger.reconciled=False;c.ledger.reasons.append(reason)
    if hasattr(c.ledger,'journal_failure'):return
    try:c.ledger.emit('STOP',{'reason':reason})
    except Exception:pass

async def run(coordinator,signal_source,book_source,report_directory,operator_handoff,*,shutdown_timeout=1):
    c=coordinator
    if not isinstance(operator_handoff,CustodyOwner):raise ValueError('INDEPENDENT_CUSTODY_OWNER_REQUIRED')
    reports=None;tasks=[];primary=None;reason='UNKNOWN';custody=None
    try:
        c.guard()
        reports=Reports(report_directory,c.ledger,c)
        factories=[lambda:signal_source.run(c.on_btc,c.on_status),lambda:book_source.run(c.on_status),c.monitor_account]
        names=['BTC_SIGNAL_SOURCE','POLYMARKET_BOOK_SOURCE','ACCOUNT_MONITOR'];restarts=[0,0,0]
        tasks=[asyncio.create_task(factory(),name=name) for factory,name in zip(factories,names)]
        while True:
            for i,task in enumerate(tasks):
                if task.done():
                    try:
                        task.result()
                    except BaseException as exc:
                        retry=transient_availability(exc) and not c.ledger.stop and not c.busy and c.ledger.active is None and not any(c.ledger.positions.values()) and restarts[i]<3
                        try:
                            c.ledger.emit('BACKGROUND_TASK_ENDED',{
                                'task_name':task.get_name(),
                                'exception_type':type(exc).__name__,
                                'message_redacted':'[REDACTED]',
                                'transient':retry,
                                'restart_attempted':retry,
                            })
                        except BaseException:pass  # ledger retains the independent journal failure
                        if retry and not c.ledger.stop:
                            c.ledger.stop_new_entries=True;c.ledger.reconciled=False
                            c.on_status('BTC_RECONNECT' if i==0 else 'WS_DISCONNECT')
                            restarts[i]+=1
                            tasks[i]=asyncio.create_task(factories[i](),name=names[i])
                            continue
                        raise
                    raise RuntimeError('BACKGROUND_TASK_ENDED:'+task.get_name())
            reports.hourly()
            if time.monotonic()-c.arm.started_monotonic>=TARGET_RUNTIME_SECONDS:c.ledger.halt('EXPERIMENT_EXPIRED')
            if c.kill_path.exists() and not c.ledger.stop:c.ledger.halt('MANUAL_KILL')
            if c.ledger.attempts>=4 and not c.busy:c.ledger.halt('ENTRY_ATTEMPT_LIMIT')
            if c.ledger.stop_new_entries and not c.ledger.stop and not c.busy:
                if c.v1['errors']:raise (c.v1.get('failures') or [RuntimeError('STRATEGY_TASK_FAILED')])[0]
                qualified=await c.recover_entries()
                if not qualified:
                    c.ledger.emit('RECOVERY_WAIT',{'reasons':c.ledger.reasons.copy(),'stop_new_entries':True,'waiting_for_reconciliation':True,'qualified':qualified})
                await asyncio.sleep(1)
                continue
            if c.v1['errors']:raise (c.v1.get('failures') or [RuntimeError('STRATEGY_TASK_FAILED')])[0]
            if c.ledger.stop and not c.busy:
                reason=c.ledger.reasons[-1];break
            await asyncio.sleep(.1)
    except BaseException as exc:
        primary=exc;reason='SUPERVISOR_EXCEPTION:'+type(exc).__name__
        stop_memory(c,reason)
    finally:
        # Transfer local responsibility synchronously BEFORE any fallible await/write.
        # Pending strategy/order may still produce evidence: external custody is mandatory.
        unsafe=c.busy or c.v1['pending'] or not c.ledger.reconciled or any(c.ledger.positions.values()) or c.ledger.active is not None
        if unsafe:custody=operator_handoff.retain(c)
        for task in [*tasks,*c.v1['pending']]:task.cancel()
        try:
            if tasks or c.v1['pending']:
                _,pending=await asyncio.wait(set(tasks)|set(c.v1['pending']),timeout=shutdown_timeout)
                if pending:operator_handoff.errors.append('SHUTDOWN_TASKS_STILL_PENDING')
            if custody is not None:await asyncio.wait({custody},timeout=shutdown_timeout)
        except asyncio.CancelledError as exc:
            if primary is None:primary=exc
            # No forwarding cancellation to independent owner; it retains a strong reference.
        for task in tasks:
            if task.done() and not task.cancelled():
                try:task.result()
                except BaseException:pass
        try:
            if reports is not None:reports.final(reason)
            c.ledger.checkpoint()
        except Exception as exc:
            operator_handoff.errors.append('FINAL_EVIDENCE:'+type(exc).__name__)
            if primary is None:primary=exc
    if primary is not None:raise primary
    return reports.snapshot(reason)
