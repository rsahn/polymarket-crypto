"""Bounded reconnection of the public diagnostic stream; no timestamp repair."""
import asyncio
import math
from copy import deepcopy


async def run_with_recovery(stream, *, connect_factory=None, max_reconnects=2,
                            delay_seconds=0.25):
    if (type(max_reconnects) is not int or not 0 <= max_reconnects <= 2 or
            type(delay_seconds) not in (int, float) or
            not math.isfinite(delay_seconds) or not 0 <= delay_seconds <= 5):
        raise ValueError('INVALID_WS_RECOVERY_POLICY')
    recovery = dict(status='RUNNING', max_reconnects=max_reconnects, attempts=[])
    stream.diagnostics['recovery'] = recovery
    recoverable = {'BOOK_REGRESSION', 'CONNECTION_CLOSED', 'NETWORK_OS_ERROR',
                   'RECEIVE_OR_CONNECT_TIMEOUT'}
    try:
        for attempt in range(max_reconnects + 1):
            if stream.clock() >= stream.expiry:
                stream.failure = 'MARKET_EXPIRED'
                recovery['status'] = 'MARKET_EXPIRED'
                return
            # run closes the previous socket and clears usable books before returning.
            # Each connection starts a new generation and needs two full snapshots.
            if connect_factory is None:
                await stream.run()
            else:
                await stream.run(connect_factory=connect_factory)
            recovery['attempts'].append(dict(attempt=attempt + 1,
                generation=stream.generation, reason=stream.failure,
                regression_event=deepcopy(stream.diagnostics.get('regression_event')),
                finished_ms=stream.clock()))
            if stream.failure not in recoverable:
                recovery['status'] = 'NON_RECOVERABLE'
                return
            if attempt == max_reconnects:
                recovery['status'] = 'RETRY_LIMIT'
                return
            recovery['status'] = 'BACKOFF'
            await asyncio.sleep(delay_seconds)
            recovery['status'] = 'RUNNING'
    except asyncio.CancelledError:
        recovery['status'] = 'CANCELLED'
        raise
    finally:
        stream.disconnect()
