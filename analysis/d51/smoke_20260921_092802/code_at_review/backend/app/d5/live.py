"""Public-feed SHADOW collector. --seconds bounds a smoke test; 0 runs until Ctrl+C."""
from __future__ import annotations

import argparse
import asyncio
import time
import shutil
from dataclasses import asdict
from pathlib import Path

from app.collectors.binance import BinanceCollector
from app.collectors.polymarket import PolymarketMarketDiscovery
from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from .features import BTCFeatures
from .identity import MarketIdentity, assert_shadow
from .observer import Observer
from .store import Store

ROOT = Path(__file__).resolve().parents[3]


def now_ms():
    return time.time_ns()//1_000_000


async def run(args):
    assert_shadow()
    store = Store(args.db, {'mode':'SHADOW','depth_levels':20,'seconds':args.seconds,
                            'reconnect_after':args.reconnect_after,'strategy':'NO_TRADE','capital':500,
                            'timestamp_contract':getattr(args,'timestamp_contract','legacy')},
                  compress_payloads=getattr(args,'compress_payloads',False))
    observer, btc = Observer(store), BTCFeatures()
    latest, generations, forced = {}, {'5m':0,'15m':0}, set()
    began = time.monotonic()
    status = 'STOPPED'
    progress = getattr(args, 'on_progress', None)
    if progress:
        progress({'session_id':store.session_id,'elapsed_seconds':0,'counts':{},'last_books':{}})

    async def on_btc(tick):
        _, available = store.btc(tick)
        btc.update(available, asdict(tick))

    async def on_btc_status(kind, payload):
        store.event(kind,payload,received_ts_ms=now_ms())

    async def market_loop(duration):
        previous = None
        while True:
            try:
                markets = await asyncio.to_thread(PolymarketMarketDiscovery.get_active_btc_markets,
                                                   verify_tls=True,raise_errors=True)
                market = next((m for m in markets if m['market_key']==duration and
                               m.get('expiry_ts_ms',0)>now_ms()), None)
                if market is None:
                    store.event('DISCOVERY_EMPTY',{'duration':duration},received_ts_ms=now_ms())
                    print(f'D5 SHADOW {duration} WAITING_BOOK: discovery has no active market',flush=True)
                    await asyncio.sleep(3)
                    continue
                identity = MarketIdentity.from_market(market)
            except Exception as exc:
                store.event('DISCOVERY_ERROR',{'duration':duration,'error':str(exc)},received_ts_ms=now_ms())
                print(f'D5 SHADOW discovery error {duration}: {exc}',flush=True)
                await asyncio.sleep(3)
                continue
            if previous and previous != identity:
                store.event('ROTATION',{'duration':duration,'previous_slug':previous.market_slug,
                                       'next_slug':identity.market_slug},received_ts_ms=now_ms())
                print(f'D5 ROTATION {duration}: {previous.market_slug} -> {identity.market_slug}',flush=True)
            previous = identity
            retries = 0
            while now_ms() < identity.expiry_ts_ms:
                generations[duration] += 1
                generation = generations[duration]
                observer.activate(identity,generation,now_ms(),market.get('metadata'))
                latest.pop(duration,None)
                session_began = time.monotonic()
                last_valid = session_began
                active_printed = False

                async def on_book(snapshot):
                    nonlocal last_valid, active_printed
                    # Collector contains a frozen identity. Never relabel an incoming snapshot.
                    eid = observer.observe(identity,generation,snapshot,btc.at(now_ms()),now_ms())
                    if eid is not None:
                        last_valid = time.monotonic()
                        latest[duration] = snapshot
                        if not active_printed:
                            print(f'D5 SHADOW {duration} ACTIVE slug={identity.market_slug} '
                                  f'condition={identity.condition_id} tokens={identity.token_up}/{identity.token_down}',flush=True)
                            active_printed = True

                collector = PolymarketOrderbookCollector(duration,{'UP':identity.token_up,'DOWN':identity.token_down},
                                                          on_book,identity.expiry_ts_ms,identity=identity,
                                                          timestamp_contract=getattr(args,"timestamp_contract","legacy"))
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
                    store.event('WS_ERROR',{'error':str(exc)},received_ts_ms=now_ms(),
                                identity=identity,generation=generation)
                finally:
                    # Invalidate callback identity/generation BEFORE awaiting task cancellation.
                    if observer.active.get(duration)==(identity,generation):
                        observer.active.pop(duration)
                    if identity.key not in observer.retired:
                        observer.invalidate(identity,now_ms(),reason)
                    latest.pop(duration,None)
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
                    store.flush()
                if reason=='EXPIRE':
                    observer.retired.add(identity.key)
                    break
                retries += 1
                store.event('RECONNECT',{'reason':reason},received_ts_ms=now_ms(),identity=identity,generation=generation)
                await asyncio.sleep(min(2.,retries*.25))

    async def housekeeping():
        printed = 0.
        reported = 0.
        while True:
            observer.expire(now_ms())
            store.flush()
            if time.monotonic()-reported >= 30:
                reported = time.monotonic()
                free = shutil.disk_usage(store.path.parent).free
                if free < getattr(args,'min_free_bytes',0):
                    raise RuntimeError('D5_DISK_RESERVE_REACHED')
                store.event('CLOCK_SAMPLE',{'wall_ts_ms':now_ms(),'monotonic_ns':time.monotonic_ns()},
                            received_ts_ms=now_ms())
                if progress:
                    progress({'session_id':store.session_id,'elapsed_seconds':reported-began,
                              'counts':dict(store.counts),'free_bytes':free,
                              'last_books':{d:{'slug':s['market_slug'],'received_ts_ms':s['received_ts_ms']}
                                            for d,s in latest.items()}})
            if time.monotonic()-printed >= 10:
                printed = time.monotonic()
                for duration,snapshot in list(latest.items()):
                    up, down = snapshot['up'],snapshot['down']
                    print(f"D5 SHADOW {duration} slug={snapshot['market_slug']} condition={snapshot['condition_id']} "
                          f"UP={up['bid']}/{up['ask']} DOWN={down['bid']}/{down['ask']} "
                          f"BTC={btc.at(now_ms())['btc_price']} inventory=0/0 paired=0 directional=0 cash=500 "
                          f"strategy=NO_TRADE",flush=True)
            await asyncio.sleep(.5)

    stop_event = getattr(args, 'stop_event', None)
    stop_waiter = asyncio.create_task(stop_event.wait()) if stop_event is not None else None
    tasks = [asyncio.create_task(BinanceCollector('btcusdt',on_btc,on_btc_status).run()),
             asyncio.create_task(market_loop('5m')),asyncio.create_task(market_loop('15m')),
             asyncio.create_task(housekeeping())]
    print(f'D5 SHADOW session={store.session_id} db={store.path} REAL_ORDERS=DISABLED',flush=True)
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
        collection_stop_ms = now_ms()
        collection_seconds = time.monotonic()-began
        store.event('COLLECTION_STOP',{'elapsed_seconds':collection_seconds},received_ts_ms=collection_stop_ms)
        for task in tasks:
            task.cancel()
        cleanup = await asyncio.gather(*tasks,return_exceptions=True)
        if stop_waiter is not None:
            stop_waiter.cancel()
            await asyncio.gather(stop_waiter,return_exceptions=True)
        cleanup_errors = [str(x) for x in cleanup if isinstance(x,BaseException) and not isinstance(x,asyncio.CancelledError)]
        if cleanup_errors:
            status = 'FAILED'
        store.event('SESSION_END',{'elapsed_seconds':time.monotonic()-began,
                                 'collection_seconds':collection_seconds,
                                 'collection_stop_ts_ms':collection_stop_ms,
                                 'cleanup_errors':cleanup_errors},received_ts_ms=now_ms())
        open_anchors = store.db.execute("SELECT count(*) FROM anchors WHERE session_id=? AND status='OPEN'",(store.session_id,)).fetchone()[0]
        if open_anchors:
            status = 'FAILED'
        store.close(status)
        print('D5 SHADOW stopped, buffers committed.',flush=True)
    return {'session_id':store.session_id,'elapsed_seconds':time.monotonic()-began,
            'collection_seconds':collection_seconds,'counts':dict(store.counts),'status':status}


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
