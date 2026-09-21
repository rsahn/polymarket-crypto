"""Public-feed SHADOW collector. --seconds bounds a smoke test; 0 runs until Ctrl+C."""
from __future__ import annotations

import argparse
import asyncio
import time
import shutil
from dataclasses import asdict
from pathlib import Path

from app.collectors.binance import BinanceCollector
from app.collectors.stage_timing import StageTiming
from app.collectors.polymarket import PolymarketMarketDiscovery
from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from .identity import MarketIdentity, assert_shadow
from .writer_process import ProcessWriter

ROOT = Path(__file__).resolve().parents[3]


def now_ms():
    return time.time_ns()//1_000_000


async def run(args):
    assert_shadow()
    writer = ProcessWriter(args.db, config={'depth_levels':20,'seconds':args.seconds,
        'reconnect_after':args.reconnect_after,'timestamp_contract':getattr(args,'timestamp_contract','legacy')})
    session_id = await writer.start()
    latest, generations, forced = {}, {'5m':0,'15m':0}, set()
    feed_timing = {}
    performance = StageTiming() if getattr(args, "timestamp_contract", "legacy") == "D5.1" else None
    began = time.monotonic()
    status = 'STOPPED'
    stopping = False
    stop_marker_sequence = None
    progress = getattr(args, 'on_progress', None)
    if progress:
        progress({'session_id':session_id,'elapsed_seconds':0,'counts':{},'last_books':{},'writer':writer.stats()})

    async def on_btc(tick):
        if stopping:
            writer.submit({'kind':'REJECT','received_ts_ms':tick.recv_ts_ms,'event_ts_ms':tick.event_ts_ms,
                           'payload':{'reason':'COLLECTION_STOP_FENCE','feed':'BTC','tick':asdict(tick)}})
            return
        writer.submit({'kind':'BTC','received_ts_ms':tick.recv_ts_ms,'tick':asdict(tick)})

    async def on_btc_status(kind, payload):
        if not stopping:
            writer.submit({'kind':'EVENT','event_kind':kind,'payload':payload,'received_ts_ms':now_ms()})

    async def market_loop(duration):
        previous = None
        while True:
            try:
                markets = await asyncio.to_thread(PolymarketMarketDiscovery.get_active_btc_markets,
                                                   verify_tls=True,raise_errors=True)
                market = next((m for m in markets if m['market_key']==duration and
                               m.get('expiry_ts_ms',0)>now_ms()), None)
                if market is None:
                    writer.submit({'kind':'EVENT','event_kind':'DISCOVERY_EMPTY','payload':{'duration':duration},'received_ts_ms':now_ms()})
                    print(f'D5 SHADOW {duration} WAITING_BOOK: discovery has no active market',flush=True)
                    await asyncio.sleep(3)
                    continue
                identity = MarketIdentity.from_market(market)
            except Exception as exc:
                writer.submit({'kind':'EVENT','event_kind':'DISCOVERY_ERROR','payload':{'duration':duration,'error':str(exc)},'received_ts_ms':now_ms()})
                print(f'D5 SHADOW discovery error {duration}: {exc}',flush=True)
                await asyncio.sleep(3)
                continue
            if previous and previous != identity:
                writer.submit({'kind':'EVENT','event_kind':'ROTATION','payload':{'duration':duration,'previous_slug':previous.market_slug,
                                       'next_slug':identity.market_slug},'received_ts_ms':now_ms()})
                print(f'D5 ROTATION {duration}: {previous.market_slug} -> {identity.market_slug}',flush=True)
            previous = identity
            retries = 0
            while now_ms() < identity.expiry_ts_ms:
                generations[duration] += 1
                generation = generations[duration]
                writer.submit({'kind':'ACTIVATE','identity':identity,'generation':generation,'metadata':market.get('metadata'),'received_ts_ms':now_ms()})
                latest.pop(duration,None)
                session_began = time.monotonic()
                last_valid = session_began
                active_printed = False

                async def on_book(snapshot):
                    nonlocal last_valid, active_printed
                    if stopping:
                        writer.submit({'kind':'REJECT','received_ts_ms':snapshot['received_ts_ms'],
                                       'event_ts_ms':snapshot.get('event_ts_ms'),'identity':identity,'generation':generation,
                                       'payload':{'reason':'COLLECTION_STOP_FENCE','feed':duration,'snapshot':snapshot}})
                        return
                    writer.submit({'kind':'BOOK','received_ts_ms':snapshot['received_ts_ms'],'identity':identity,'generation':generation,'snapshot':snapshot})
                    observed_at = now_ms()
                    wire = snapshot.get('wire_event_ts_ms')
                    if wire is not None:
                        timing = feed_timing.setdefault(duration, {'observations':0,'wire_age_sum_ms':0})
                        age = snapshot['received_ts_ms']-wire
                        timing['observations'] += 1
                        timing['wire_age_sum_ms'] += age
                        timing['last_wire_age_ms'] = age
                        timing['max_wire_age_ms'] = max(timing.get('max_wire_age_ms',age),age)
                        timing['last_processing_ms'] = observed_at-snapshot['received_ts_ms']
                        timing['last_received_ts_ms'] = snapshot['received_ts_ms']
                    last_valid = time.monotonic()
                    latest[duration] = snapshot
                    if not active_printed:
                        print(f'D5 SHADOW {duration} ACTIVE slug={identity.market_slug} '
                              f'condition={identity.condition_id} tokens={identity.token_up}/{identity.token_down}',flush=True)
                        active_printed = True

                collector = PolymarketOrderbookCollector(duration,{'UP':identity.token_up,'DOWN':identity.token_down},
                                                          on_book,identity.expiry_ts_ms,identity=identity,
                                                          timestamp_contract=getattr(args,"timestamp_contract","legacy"),
                                                          performance=performance)
                task = asyncio.create_task(collector.run())
                reason = 'RECONNECT'
                try:
                    while not task.done():
                        await asyncio.sleep(.2)
                        if now_ms() >= identity.expiry_ts_ms:
                            reason = 'EXPIRE'
                            break
                        if args.reconnect_after and duration not in forced and active_printed and \
                                time.monotonic()-session_began >= args.reconnect_after:
                            forced.add(duration)
                            reason = 'FORCED_RECONNECT_TEST'
                            break
                        if time.monotonic()-last_valid > 10:
                            reason = 'STALE_BOOK_RECONNECT'
                            break
                    if task.done():
                        await task
                except asyncio.CancelledError:
                    reason = 'SESSION_END'
                    raise
                except Exception as exc:
                    writer.submit({'kind':'EVENT','event_kind':'WS_ERROR','payload':{'error':str(exc)},'received_ts_ms':now_ms(),'identity':identity,'generation':generation})
                finally:
                    writer.submit({'kind':'INVALIDATE','identity':identity,'generation':generation,'reason':reason,'received_ts_ms':now_ms()})
                    latest.pop(duration,None)
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
                    writer.submit({'kind':'FLUSH','received_ts_ms':now_ms()})
                if reason=='EXPIRE':
                    writer.submit({'kind':'EXPIRE','received_ts_ms':now_ms()})
                    break
                retries += 1
                writer.submit({'kind':'EVENT','event_kind':'RECONNECT','payload':{'reason':reason},'received_ts_ms':now_ms(),'identity':identity,'generation':generation})
                await asyncio.sleep(min(2.,retries*.25))

    async def housekeeping():
        printed = 0.
        reported = 0.
        while True:
            writer.submit({'kind':'EXPIRE','received_ts_ms':now_ms()})
            writer.submit({'kind':'FLUSH','received_ts_ms':now_ms()})
            if time.monotonic()-reported >= 30:
                reported = time.monotonic()
                free = shutil.disk_usage(Path(args.db).resolve().parent).free
                if free < getattr(args,'min_free_bytes',0):
                    raise RuntimeError('D5_DISK_RESERVE_REACHED')
                writer.submit({'kind':'EVENT','event_kind':'CLOCK_SAMPLE','payload':{'wall_ts_ms':now_ms(),'monotonic_ns':time.monotonic_ns()},'received_ts_ms':now_ms()})
                if progress:
                    progress({'session_id':session_id,'elapsed_seconds':reported-began,
                              'counts':dict((writer.last_ack or {}).get('counts',{})),'free_bytes':free,
                              'feed_timing':{d:dict(v) for d,v in feed_timing.items()},
                              'stage_timing':performance.snapshot() if performance is not None else {},'writer':writer.stats(),
                              'last_books':{d:{'slug':s['market_slug'],'received_ts_ms':s['received_ts_ms']}
                                            for d,s in latest.items()}})
            if time.monotonic()-printed >= 10:
                printed = time.monotonic()
                for duration,snapshot in list(latest.items()):
                    up, down = snapshot['up'],snapshot['down']
                    print(f"D5 SHADOW {duration} slug={snapshot['market_slug']} condition={snapshot['condition_id']} "
                          f"UP={up['bid']}/{up['ask']} DOWN={down['bid']}/{down['ask']} "
                          f"BTC=worker-owned inventory=0/0 paired=0 directional=0 cash=500 "
                          f"strategy=NO_TRADE",flush=True)
            await asyncio.sleep(.5)

    stop_event = getattr(args, 'stop_event', None)
    stop_waiter = asyncio.create_task(stop_event.wait()) if stop_event is not None else None
    tasks = [asyncio.create_task(BinanceCollector('btcusdt',on_btc,on_btc_status).run()),
             asyncio.create_task(market_loop('5m')),asyncio.create_task(market_loop('15m')),
             asyncio.create_task(housekeeping())]
    print(f'D5 SHADOW session={session_id} db={Path(args.db).resolve()} REAL_ORDERS=DISABLED',flush=True)
    try:
        if args.seconds:
            watched = tasks + ([stop_waiter] if stop_waiter else [])
            done, _ = await asyncio.wait(watched,timeout=args.seconds,return_when=asyncio.FIRST_COMPLETED)
            if stop_waiter in done:
                done.remove(stop_waiter)
                status = 'STOPPED_BY_USER_CLEAN'
            for task in done:
                await task
            if done:
                raise RuntimeError('D5 collector exited before the requested duration')
        else:
            if stop_waiter is None:
                await asyncio.gather(*tasks)
            else:
                done, _ = await asyncio.wait(tasks+[stop_waiter],return_when=asyncio.FIRST_COMPLETED)
                if stop_waiter in done:
                    done.remove(stop_waiter)
                    status = 'STOPPED_BY_USER_CLEAN'
                for task in done:
                    await task
                if done:
                    raise RuntimeError('D5 collector exited unexpectedly')
    except BaseException:
        status = 'FAILED'
        raise
    finally:
        # Fence all callbacks synchronously before cancellation can schedule siblings.
        # Late raw messages remain explicit REJECT evidence, never accepted BOOK/BTC.
        stopping = True
        collection_stop_ms = now_ms()
        stop_marker_sequence = writer.submit({'kind':'EVENT','event_kind':'COLLECTION_STOP',
            'payload':{'elapsed_seconds':time.monotonic()-began},'received_ts_ms':collection_stop_ms})
        collection_seconds = time.monotonic()-began
        for task in tasks:
            task.cancel()
        cleanup = await asyncio.gather(*tasks,return_exceptions=True)
        if stop_waiter is not None:
            stop_waiter.cancel()
            await asyncio.gather(stop_waiter,return_exceptions=True)
        cleanup_errors = [str(x) for x in cleanup if isinstance(x,BaseException) and not isinstance(x,asyncio.CancelledError)]
        if cleanup_errors:
            status = 'FAILED'
        try:
            if stop_marker_sequence is not None:
                await writer.wait_processed(stop_marker_sequence)
            ack = await writer.stop(received_ts_ms=now_ms(), status=status,
                payload={'elapsed_seconds':time.monotonic()-began,'collection_seconds':collection_seconds,
                         'collection_stop_ts_ms':collection_stop_ms}, cleanup_errors=cleanup_errors)
        except Exception:
            status = 'FAILED'
            if writer.error is not None:
                await writer.release_failed()
            raise
        print('D5 SHADOW stopped, buffers committed.',flush=True)
    return {'session_id':session_id,'elapsed_seconds':time.monotonic()-began,
            'collection_seconds':collection_seconds,'counts':dict((writer.last_ack or {}).get('counts',{})),'status':status,'writer':writer.stats()}


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'data/d5_live.db')
    parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--reconnect-after',type=float,default=0,help='One deliberate reconnect per duration for smoke testing')
    args = parser.parse_args()
    if args.seconds < 0 or args.reconnect_after < 0:
        parser.error('durations must be nonnegative')
    assert_shadow()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__=='__main__':
    cli()
