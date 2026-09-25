import asyncio
import json
import pytest
from app.live.readonly_book_stream import StreamBook
from app.live.ws_recovery import run_with_recovery


def book(token, stamp=1000):
    return dict(event_type='book', market='c', asset_id=token, timestamp=str(stamp),
                bids=[dict(price='.4', size='2')], asks=[dict(price='.6', size='2')])


class Socket:
    def __init__(self, events):
        self.events = iter(events)
        self.closed = False
    async def __aenter__(self): return self
    async def __aexit__(self, *args): self.closed = True
    async def send(self, value): pass
    async def recv(self):
        event = next(self.events, None)
        if callable(event):
            event()
            await asyncio.Future()
        if isinstance(event, Exception): raise event
        return json.dumps(event)


@pytest.mark.parametrize('kind', ['book', 'price_change'])
def test_recovery_waits_for_two_new_snapshots_and_cancels_cleanly(kind):
    async def scenario():
        s = StreamBook('m', 'c', ('a', 'b'), 5000, clock=lambda: 1050)
        old = book('a', 998) if kind == 'book' else dict(event_type='price_change', market='c',
            timestamp='998', price_changes=[dict(asset_id='a', side='BUY', price='.4', size='3')])
        ready = asyncio.Event()
        def check_ready():
            assert s.read()['synchronized'] and s.generation == 2
            assert {v['observed_ms'] for v in s.books.values()} == {1020}
            ready.set()
        class Second(Socket):
            async def recv(self):
                if 'a' in s.books and 'b' not in s.books:
                    assert not s.read()['available']
                return await super().recv()
        sockets = [Socket([book('a'), book('b'), old]), Second([book('a', 1020), book('b', 1020), check_ready])]
        calls = []
        def connect(*args, **kwargs):
            if calls: assert sockets[0].closed and not s.read()['available']
            calls.append(1)
            return sockets[len(calls)-1]
        task = asyncio.create_task(run_with_recovery(s, connect_factory=connect, delay_seconds=0))
        try:
            await asyncio.wait_for(ready.wait(), 2)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
        assert len(calls) == 2 and all(ws.closed for ws in sockets)
        assert not s.read()['available']
        assert s.diagnostics['recovery']['attempts'][0]['reason'] == 'BOOK_REGRESSION'
        assert s.diagnostics['recovery']['attempts'][0]['regression_event']['delta_ms'] == -2
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    asyncio.run(scenario())


def test_network_failure_retries_are_bounded():
    s = StreamBook('m', 'c', ('a', 'b'), 5000, clock=lambda: 1050)
    calls = []
    def connect(*a, **k):
        calls.append(1)
        return Socket([OSError('do not report raw exception')])
    asyncio.run(run_with_recovery(s, connect_factory=connect, delay_seconds=0))
    assert len(calls) == 3
    assert s.diagnostics['recovery']['status'] == 'RETRY_LIMIT'
    assert not s.read()['available']
    assert 'do not report' not in json.dumps(s.diagnostics)


def test_identity_failure_is_not_retried():
    s = StreamBook('m', 'c', ('a', 'b'), 5000, clock=lambda: 1050)
    calls = []
    def connect(*a, **k):
        calls.append(1)
        return Socket([{**book('a'), 'market': 'wrong'}])
    asyncio.run(run_with_recovery(s, connect_factory=connect, delay_seconds=0))
    assert len(calls) == 1 and s.failure == 'MARKET_IDENTITY'
    assert s.diagnostics['recovery']['status'] == 'NON_RECOVERABLE'


def test_expired_market_does_not_connect():
    s = StreamBook('m', 'c', ('a', 'b'), 1000, clock=lambda: 1050)
    def connect(*a, **k): raise AssertionError('expired connection')
    asyncio.run(run_with_recovery(s, connect_factory=connect))
    assert s.diagnostics['recovery']['status'] == 'MARKET_EXPIRED'


def test_cancel_during_backoff_never_reconnects():
    async def scenario():
        s = StreamBook('m', 'c', ('a', 'b'), 5000, clock=lambda: 1050)
        calls = []
        def connect(*a, **k):
            calls.append(1)
            return Socket([OSError('offline')])
        task = asyncio.create_task(run_with_recovery(s, connect_factory=connect, delay_seconds=5))
        async def wait_backoff():
            while s.diagnostics.get('recovery', {}).get('status') != 'BACKOFF':
                await asyncio.sleep(0)
        await asyncio.wait_for(wait_backoff(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert len(calls) == 1 and not s.read()['available']
    asyncio.run(scenario())


@pytest.mark.parametrize('kwargs', [{'max_reconnects': -1}, {'max_reconnects': True},
                                  {'delay_seconds': -1}, {'delay_seconds': float('nan')}])
def test_invalid_policy_rejected(kwargs):
    s = StreamBook('m', 'c', ('a', 'b'), 5000, clock=lambda: 1050)
    with pytest.raises(ValueError): asyncio.run(run_with_recovery(s, **kwargs))
