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
CREATE TABLE IF NOT EXISTS benchmark_activity (
 id INTEGER PRIMARY KEY AUTOINCREMENT, benchmark TEXT NOT NULL, wallet TEXT NOT NULL,
 timestamp INTEGER NOT NULL, condition_id TEXT, type TEXT NOT NULL, side TEXT,
 outcome TEXT, outcome_index INTEGER, asset TEXT, size REAL, price REAL,
 usdc_size REAL, transaction_hash TEXT, title TEXT, slug TEXT, event_slug TEXT,
 is_combo INTEGER NOT NULL DEFAULT 0, raw_json TEXT NOT NULL,
 UNIQUE(benchmark, transaction_hash, timestamp, asset, side, size, price)
);
CREATE INDEX IF NOT EXISTS idx_benchmark_activity ON benchmark_activity(benchmark, timestamp);
CREATE TABLE IF NOT EXISTS benchmark_checkpoints (
 wallet TEXT PRIMARY KEY, window_start INTEGER NOT NULL, window_end INTEGER NOT NULL,
 cursor INTEGER NOT NULL, inserted_rows INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL, updated_at INTEGER NOT NULL
);
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

    async def insert_poly_snapshot(self, snapshot):
        rows = []
        for outcome in ('up', 'down'):
            quote = snapshot.get(outcome) or {}
            if quote.get('bid') is None or quote.get('ask') is None:
                continue
            rows.append((
                snapshot['market_key'], quote['token_id'], outcome.upper(),
                snapshot.get('event_ts_ms'), snapshot['recv_ts_ms'],
                quote['bid'], quote['ask'], quote.get('bid_qty'), quote.get('ask_qty'),
            ))
        if not rows:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                "INSERT INTO poly_quotes(market_id,token_id,outcome,event_ts_ms,recv_ts_ms,bid,ask,bid_qty,ask_qty) VALUES(?,?,?,?,?,?,?,?,?)",
                rows,
            )
            await db.commit()

    async def insert_benchmark_activity(self, rows):
        if not rows:
            return 0
        async with aiosqlite.connect(self.path) as db:
            before = db.total_changes
            await db.executemany(
                """INSERT OR IGNORE INTO benchmark_activity
                (benchmark,wallet,timestamp,condition_id,type,side,outcome,outcome_index,asset,size,price,usdc_size,transaction_hash,title,slug,event_slug,is_combo,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(
                    row['benchmark'], row['wallet'], row['timestamp'], row['condition_id'], row['type'], row['side'],
                    row['outcome'], row['outcome_index'], row['asset'], row['size'], row['price'], row['usdc_size'],
                    row['transaction_hash'], row['title'], row['slug'], row['event_slug'], int(row['is_combo']), row['raw_json'],
                ) for row in rows],
            )
            await db.commit()
            return db.total_changes - before

    async def get_benchmark_checkpoint(self, wallet):
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                'SELECT window_start,window_end,cursor,inserted_rows,status FROM benchmark_checkpoints WHERE wallet=?',
                (wallet,),
            )
            return await cursor.fetchone()

    async def save_benchmark_checkpoint(self, wallet, window_start, window_end, cursor, inserted_rows, status):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO benchmark_checkpoints(wallet,window_start,window_end,cursor,inserted_rows,status,updated_at)
                VALUES(?,?,?,?,?,?,strftime('%s','now'))
                ON CONFLICT(wallet) DO UPDATE SET window_start=excluded.window_start,window_end=excluded.window_end,
                cursor=excluded.cursor,inserted_rows=excluded.inserted_rows,status=excluded.status,updated_at=excluded.updated_at""",
                (wallet, window_start, window_end, cursor, inserted_rows, status),
            )
            await db.commit()

    async def benchmark_total(self, wallet):
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute('SELECT count(*) FROM benchmark_activity WHERE benchmark=?', (wallet,))
            return (await cursor.fetchone())[0]
