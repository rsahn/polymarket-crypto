from pathlib import Path
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS btc_ticks (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, symbol TEXT,
 event_ts_ms INTEGER, recv_ts_ms INTEGER NOT NULL, price REAL NOT NULL,
 bid REAL, ask REAL, bid_qty REAL, ask_qty REAL
);
CREATE INDEX IF NOT EXISTS idx_btc_recv ON btc_ticks(recv_ts_ms);
CREATE TABLE IF NOT EXISTS poly_quotes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, market_id TEXT NOT NULL, token_id TEXT NOT NULL,
 outcome TEXT NOT NULL, event_ts_ms INTEGER, recv_ts_ms INTEGER NOT NULL,
 bid REAL NOT NULL, ask REAL NOT NULL, bid_qty REAL, ask_qty REAL
);
CREATE INDEX IF NOT EXISTS idx_poly_market_recv ON poly_quotes(market_id, recv_ts_ms);
CREATE TABLE IF NOT EXISTS signals (
 id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT NOT NULL, market_id TEXT NOT NULL,
 ts_ms INTEGER NOT NULL, side TEXT NOT NULL, score REAL, expected_edge REAL,
 metadata_json TEXT
);
CREATE TABLE IF NOT EXISTS paper_trades (
 id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT NOT NULL, market_id TEXT NOT NULL,
 opened_ts_ms INTEGER NOT NULL, closed_ts_ms INTEGER, side TEXT NOT NULL,
 qty REAL NOT NULL, entry_price REAL NOT NULL, exit_price REAL,
 fees REAL DEFAULT 0, slippage REAL DEFAULT 0, pnl REAL, status TEXT NOT NULL
);
"""

class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def insert_btc(self, t):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO btc_ticks(source,symbol,event_ts_ms,recv_ts_ms,price,bid,ask,bid_qty,ask_qty) VALUES(?,?,?,?,?,?,?,?,?)",
                (t.source,t.symbol,t.event_ts_ms,t.recv_ts_ms,t.price,t.bid,t.ask,t.bid_qty,t.ask_qty))
            await db.commit()
