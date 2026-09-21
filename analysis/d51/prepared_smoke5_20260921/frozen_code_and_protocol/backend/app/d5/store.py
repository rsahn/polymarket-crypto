from __future__ import annotations

import hashlib
from collections import Counter, OrderedDict
import struct
import json
import sqlite3
import subprocess
import time
import uuid
import zlib
from dataclasses import asdict
from pathlib import Path

from .identity import assert_shadow

SCHEMA_VERSION = 1


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def json_text(value):
    # Schema 2 stores large JSON losslessly as zlib BLOBs; schema 1 remains readable.
    return zlib.decompress(value).decode('utf-8') if isinstance(value, bytes) else value


def decode(value):
    return json.loads(json_text(value))


def book_before_expiry(snapshot, identity, available):
    timestamps = [available, snapshot['received_ts_ms'], snapshot.get('event_ts_ms')]
    timestamps.extend(snapshot[side].get('event_ts_ms') for side in ('up', 'down'))
    return all(ts < identity.expiry_ts_ms for ts in timestamps if ts is not None)


def code_version():
    root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        commit = 'unavailable'
    sha = hashlib.sha256()
    for p in sorted((root/'backend/app').rglob('*')):
        if p.suffix in ('.py','.sql'):
            sha.update(str(p.relative_to(root)).encode())
            sha.update(p.read_bytes())
    return commit+':working-tree-sha256:'+sha.hexdigest()


class Store:
    """One event-loop writer, batched commits. No historical DB is opened."""
    def __init__(self, path, config=None, *, compress_payloads=False):
        assert_shadow()
        self.schema_version = 2 if compress_payloads else 1
        self.path = Path(path).resolve()
        if self.path.name in ('c3_shadow_live.db','poly_quant.db','paper_live.db','snapshot.db'):
            raise ValueError('Historical database is audit-only')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables and 'schema_info' not in tables:
            self.db.close()
            raise ValueError('Refusing non-D5 database')
        if 'schema_info' in tables and self.db.execute('SELECT version FROM schema_info').fetchall() != [(self.schema_version,)]:
            self.db.close()
            raise ValueError('Unsupported D5 schema')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        schema = 'schema_v2.sql' if self.schema_version == 2 else 'schema.sql'
        self.db.executescript(Path(__file__).with_name(schema).read_text())
        self.session_id = str(uuid.uuid4())
        self.last_available = 0
        self.counts = Counter()
        self.depth_cache = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0
        self.db.execute('INSERT INTO sessions VALUES(?,?,NULL,?,?,?,?,?)',
                        (self.session_id, time.time_ns()//1_000_000, code_version(), self.schema_version, 'SHADOW',
                         'RUNNING', encode(config or {})))
        self.db.commit()

    def _pack_uncached(self, value):
        text = encode(value)
        if self.schema_version == 2 and len(text) >= 512:
            compressed = zlib.compress(text.encode('utf-8'), 1)
            if len(compressed) < len(text.encode('utf-8')):
                return compressed
        return text

    def pack(self, value):
        if self.schema_version != 2 or type(value) is not list or len(value) > 20:
            return self._pack_uncached(value)
        flat = []
        for level in value:
            if type(level) not in (tuple, list) or len(level) != 2:
                return self._pack_uncached(value)
            if type(level[0]) is not float or type(level[1]) is not float:
                return self._pack_uncached(value)
            flat.extend(level)
        key = struct.pack('<' + 'd' * len(flat), *flat)
        if key in self.depth_cache:
            self.cache_hits += 1
            self.depth_cache.move_to_end(key)
            return self.depth_cache[key]
        self.cache_misses += 1
        packed = self._pack_uncached(value)
        self.depth_cache[key] = packed
        if len(self.depth_cache) > 1024:
            self.depth_cache.popitem(last=False)
        return packed

    def market(self, identity, metadata):
        fields = tuple(identity.fields().values())
        old = self.db.execute('SELECT market_duration,market_slug,condition_id,token_up,token_down,expiry_ts_ms '
                              'FROM markets WHERE market_slug=? OR condition_id=?',
                              (identity.market_slug, identity.condition_id)).fetchall()
        if old and old != [fields]:
            raise ValueError('CROSS_MARKET_REJECT: immutable market mapping changed')
        self.db.execute('INSERT OR IGNORE INTO markets VALUES(?,?,?,?,?,?,?)',
                        (identity.condition_id, identity.market_slug, identity.market_duration,
                         identity.token_up, identity.token_down, identity.expiry_ts_ms, encode(metadata)))

    def event(self, kind, payload, *, received_ts_ms, event_ts_ms=None, identity=None, generation=None,
              available_ts_ms=None):
        available = max(self.last_available, int(available_ts_ms if available_ts_ms is not None else
                                                time.time_ns()//1_000_000), int(received_ts_ms))
        self.last_available = available
        fields = (identity.market_duration,identity.market_slug,identity.condition_id,
                  identity.token_up,identity.token_down) if identity else (None,)*5
        cur = self.db.execute('''INSERT INTO events(session_id,kind,event_ts_ms,received_ts_ms,
            available_ts_ms,market_duration,market_slug,condition_id,token_up,token_down,generation,payload_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            (self.session_id,kind,event_ts_ms,received_ts_ms,available,*fields,generation,self.pack(payload)))
        self.counts[kind] += 1
        return cur.lastrowid, available

    def book(self, snapshot, identity, generation, now_ms):
        if not identity.matches(snapshot):
            raise ValueError('CROSS_MARKET_REJECT')
        now_ms = max(self.last_available, now_ms, snapshot['received_ts_ms'])
        if not book_before_expiry(snapshot, identity, now_ms):
            raise ValueError('POST_EXPIRY_REJECT')
        eid, available = self.event('BOOK', snapshot, received_ts_ms=snapshot['received_ts_ms'],
                                    event_ts_ms=snapshot.get('event_ts_ms'), identity=identity,
                                    generation=generation, available_ts_ms=now_ms)
        for side in ('UP','DOWN'):
            q = snapshot[side.lower()]
            spread = q['ask']-q['bid'] if q.get('ask') is not None and q.get('bid') is not None else None
            self.db.execute('INSERT INTO book_sides VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (eid,side,q['token_id'],q.get('event_ts_ms'),
                             q.get('received_ts_ms',snapshot['received_ts_ms']) if snapshot.get('timestamp_contract')=='D5.1' else snapshot['received_ts_ms'],
                             q.get('bid'),q.get('ask'),q.get('bid_qty',0),q.get('ask_qty',0),spread,
                             self.pack(q.get('bids',[])),self.pack(q.get('asks',[])),
                             q.get('source_hash'),str(q['sequence']) if q.get('sequence') is not None else None))
        return eid, available

    def btc(self, tick, now_ms=None):
        return self.event('BTC', asdict(tick), received_ts_ms=tick.recv_ts_ms,
                          event_ts_ms=tick.event_ts_ms, available_ts_ms=now_ms)

    def flush(self):
        self.db.commit()

    def close(self, status='STOPPED'):
        now = time.time_ns()//1_000_000
        self.db.execute("UPDATE anchors SET status='CLOSED',closed_at_ms=?,close_reason='SESSION_END' "
                        "WHERE session_id=? AND status='OPEN'", (now,self.session_id))
        self.db.execute('UPDATE sessions SET ended_at_ms=?,status=? WHERE session_id=?',
                        (now,status,self.session_id))
        self.db.commit()
        self.db.close()
