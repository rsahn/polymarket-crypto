"""Bounded read-only connection preparation; returns no business observations.

Public chain-id reads exercise the existing RPC pool. Account reads exercise
the existing CLOB/Data pools. Every decision read must still be acquired anew.
"""
import asyncio
from .production_readonly import now_ms
from .latency_trace import measured_thread, measured_await


async def warm_readonly(rpc, account_reader):
    start=now_ms()
    async def collect():
        return await asyncio.gather(
            measured_await('warmup.account',account_reader()),
            *(measured_thread('warmup.rpc',rpc.call,'eth_chainId',[]) for _ in range(8)),
            return_exceptions=True)
    task=asyncio.create_task(collect())
    try:
        results=await asyncio.shield(task)
    except asyncio.CancelledError:
        # Drain bounded reads before caller closes the shared pools.
        while not task.done():
            try:await asyncio.shield(task)
            except asyncio.CancelledError:continue
            except Exception:break
        if not task.cancelled():task.exception()
        raise
    if isinstance(results[0],BaseException) or any(v!='0x89' for v in results[1:]):
        raise ValueError('READ_ONLY_WARMUP_FAILED')
    # Deliberately return no account values or observation timestamps.
    return dict(status='READS_COMPLETED_REUSE_NOT_GUARANTEED',started_ms=start,
                finished_ms=now_ms(),rpc_reads=8,account_generations=1,
                account_values_discarded=True,retries=0)
