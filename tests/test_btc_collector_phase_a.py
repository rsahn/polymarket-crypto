"""Historical Phase A intent, migrated to the tracked app collector/storage API.
The original imports never existed in the initial tracked tree (7cb0198).
"""
import asyncio
import json
import sqlite3
import pytest
from app.collectors.binance import BinanceCollector
from app.storage.db import Database


def test_db_initializes_required_tables(tmp_path):
    path=tmp_path/"phase_a.db"
    asyncio.run(Database(str(path)).init())
    with sqlite3.connect(path) as db:
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"btc_ticks","poly_quotes","signals","paper_trades"}<=tables


def test_trade_and_booktick_are_normalized(tmp_path,monkeypatch):
    path=tmp_path/"phase_a.db"
    messages=[dict(b="63998.50",B="1.5",a="64001.50",A="2.1"),
              dict(e="aggTrade",E=1700000000000,p="64000.00",a=123)]
    class Socket:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        def __aiter__(self):return self
        async def __anext__(self):
            if not messages:raise StopAsyncIteration
            return json.dumps({"data":messages.pop(0)})
    monkeypatch.setattr("app.collectors.binance.websockets.connect",lambda *a,**k:Socket())
    async def run():
        store=Database(str(path));await store.init()
        async def tick(value):
            assert value.trade_id==123
            await store.insert_btc(value)
            raise asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):await BinanceCollector("BTCUSDT",tick).run()
    asyncio.run(run())
    with sqlite3.connect(path) as db:
        rows=db.execute("SELECT source,symbol,event_ts_ms,price,bid,ask,bid_qty,ask_qty FROM btc_ticks").fetchall()
    assert rows==[("binance","btcusdt",1700000000000,64000.0,63998.5,64001.5,1.5,2.1)]


def test_callback_failure_is_not_relabelled_network(monkeypatch):
    error=ValueError('fixture strategy failure');statuses=[]
    class Socket:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        def __aiter__(self):return self
        async def __anext__(self):return json.dumps(dict(e='aggTrade',E=1,p='100',a=1))
    monkeypatch.setattr('app.collectors.binance.websockets.connect',lambda *a,**k:Socket())
    async def case():
        async def tick(value):raise error
        async def status(kind,details):statuses.append(kind)
        with pytest.raises(ValueError) as raised:await BinanceCollector('BTCUSDT',tick,status).run()
        assert raised.value is error and statuses==['BTC_CONNECTED']
    asyncio.run(case())


def test_clean_close_reports_disconnect(monkeypatch):
    statuses=[]
    class Socket:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        def __aiter__(self):return self
        async def __anext__(self):raise StopAsyncIteration
    monkeypatch.setattr('app.collectors.binance.websockets.connect',lambda *a,**k:Socket())
    async def case():
        async def tick(value):raise AssertionError('no tick expected')
        async def status(kind,details):
            statuses.append(kind)
            if kind=='BTC_RECONNECT':raise asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):await BinanceCollector('BTCUSDT',tick,status).run()
        assert statuses==['BTC_CONNECTED','BTC_RECONNECT']
    asyncio.run(case())
