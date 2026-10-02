"""Trading supervision; independent injected custody owner outlives this task."""
import asyncio,time
from .reports import Reports
from .custody import CustodyOwner

TARGET_RUNTIME_SECONDS=259200

def stop_memory(c,reason):
    c.ledger.stop=True;c.ledger.reconciled=False;c.ledger.reasons.append(reason)
    try:c.ledger.emit('STOP',{'reason':reason})
    except Exception:pass

async def run(coordinator,signal_source,book_source,report_directory,operator_handoff,*,shutdown_timeout=1):
    c=coordinator
    if not isinstance(operator_handoff,CustodyOwner):raise ValueError('INDEPENDENT_CUSTODY_OWNER_REQUIRED')
    reports=None;tasks=[];primary=None;reason='UNKNOWN';custody=None
    try:
        c.guard()
        reports=Reports(report_directory,c.ledger,c)
        tasks=[asyncio.create_task(signal_source.run(c.on_btc,c.on_status)),
               asyncio.create_task(book_source.run(c.on_status)),asyncio.create_task(c.monitor_account())]
        while True:
            for task in tasks:
                if task.done():
                    task.result();raise RuntimeError('BACKGROUND_TASK_ENDED')
            reports.hourly()
            if time.monotonic()-c.arm.started_monotonic>=259200:c.ledger.halt('EXPERIMENT_EXPIRED')
            if c.kill_path.exists() and not c.ledger.stop:c.ledger.halt('MANUAL_KILL')
            if c.ledger.attempts>=4 and not c.busy:c.ledger.halt('ENTRY_ATTEMPT_LIMIT')
            if c.ledger.stop_new_entries and not c.ledger.stop and not c.busy:
                # Recovery mode: wait for full requalification before clearing V1 transient errors
                qualified=(
                    c.ledger.reconciled
                    and c.ledger.exposure_known
                    and not any(c.ledger.positions.values())
                    and c.ledger.active is None
                    and c.ledger.account_qualified
                    and c._post_reconnect_verified
                )
                if qualified:
                    _TRANSIENT_TYPES={'ValueError','KeyError'}
                    c.v1['errors']=[e for e in c.v1['errors'] if e not in _TRANSIENT_TYPES]
                    c.ledger.stop_new_entries=False
                    c.ledger.emit('RECOVERY_COMPLETE',{'cleared_transient_errors':True,'remaining_v1_errors':c.v1['errors'].copy()})
                else:
                    c.ledger.emit('RECOVERY_WAIT',{'reasons':c.ledger.reasons.copy(),'stop_new_entries':True,'waiting_for_reconciliation':True,'qualified':qualified})
                await asyncio.sleep(1)
                continue
            if c.v1['errors']:raise RuntimeError('STRATEGY_TASK_FAILED')
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
