from __future__ import annotations

import math
from collections import defaultdict

from .store import book_before_expiry, encode


class Observer:
    """Persist all T0 anchors; no scheduled C3 trading or hedge selection."""
    def __init__(self, store):
        self.store = store
        self.active = {}
        self.retired = set()
        self.anchors = defaultdict(list)  # (condition_id, market_slug), never duration
        self.last_anchor = {}
        self.last_received = {}
        self.seen = {}

    def activate(self, identity, generation, now_ms, metadata=None):
        old = self.active.get(identity.market_duration)
        if identity.key in self.retired:
            raise ValueError('CROSS_MARKET_REJECT: retired identity')
        self.store.market(identity, metadata or {})
        if old and old[0] != identity:
            self.invalidate(old[0], now_ms, 'ROTATED')
            self.retired.add(old[0].key)
        if old and old[0] == identity:
            self.invalidate(identity, now_ms, 'RECONNECT')
        self.active[identity.market_duration] = (identity,generation)
        self.last_received.pop(identity.key, None)
        self.seen.pop(identity.key, None)
        self.store.event('ACTIVATE', {'identity':identity.fields()},received_ts_ms=now_ms,
                         identity=identity,generation=generation,available_ts_ms=now_ms)

    def invalidate(self, identity, now_ms, reason):
        ids = self.anchors.pop(identity.key, [])
        self.store.db.execute("UPDATE anchors SET status='CLOSED',closed_at_ms=?,close_reason=? "
                              "WHERE session_id=? AND anchor_condition_id=? AND anchor_market_slug=? AND status='OPEN'",
                              (now_ms,reason,self.store.session_id,*identity.key))
        self.last_anchor.pop(identity.key, None)
        self.store.event(reason, {'closed_anchors':len(ids)}, received_ts_ms=now_ms,
                         identity=identity,available_ts_ms=now_ms)
        assert identity.key not in self.anchors

    def expire(self, now_ms):
        for duration,(identity,generation) in list(self.active.items()):
            if now_ms >= identity.expiry_ts_ms:
                self.invalidate(identity,now_ms,'EXPIRE')
                self.retired.add(identity.key)
                del self.active[duration]

    def reject(self, identity, snapshot, now, reason):
        self.store.event('REJECT', {'reason':reason, 'snapshot':snapshot},
                         received_ts_ms=int(snapshot.get('received_ts_ms',now)),identity=identity,
                         event_ts_ms=snapshot.get('event_ts_ms'),available_ts_ms=now)
        return None

    def observe(self, identity, generation, snapshot, features, now_ms):
        active = self.active.get(identity.market_duration)
        if active != (identity,generation):
            return self.reject(identity,snapshot,now_ms,'CROSS_MARKET_REJECT')
        if snapshot.get('reject_reason'):
            return self.reject(identity,snapshot,now_ms,snapshot['reject_reason'])
        if not identity.matches(snapshot):
            return self.reject(identity,snapshot,now_ms,'CROSS_MARKET_REJECT')
        received = snapshot['received_ts_ms']
        now_ms = max(now_ms, received, self.store.last_available)
        if not book_before_expiry(snapshot, identity, now_ms):
            self.expire(now_ms)
            return self.reject(identity,snapshot,now_ms,'POST_EXPIRY_REJECT')
        if received < self.last_received.get(identity.key, -1):
            return self.reject(identity,snapshot,now_ms,'OUT_OF_ORDER')
        fingerprint = snapshot.get('wire_hash') or encode(snapshot)
        if fingerprint == self.seen.get(identity.key):
            return self.reject(identity,snapshot,now_ms,'DUPLICATE_EVENT')
        # Missing/zero depth is retained. Crossed/nonfinite prices are not tradable books.
        for side in ('up','down'):
            q = snapshot[side]
            vals = [q.get(k) for k in ('bid','ask','bid_qty','ask_qty')]
            if any(v is None for v in vals):
                return self.reject(identity,snapshot,now_ms,'INCOMPLETE_BOOK')
            if not all(math.isfinite(v) for v in vals) or not 0 <= vals[0] < vals[1] <= 1 or min(vals[2:]) < 0:
                return self.reject(identity,snapshot,now_ms,'INVALID_BOOK')
        self.last_received[identity.key] = received
        self.seen[identity.key] = fingerprint
        eid, available = self.store.book(snapshot,identity,generation,now_ms)
        if available-self.last_anchor.get(identity.key,-10**20) >= 1000:
            for side in ('UP','DOWN'):
                cur = self.store.db.execute('''INSERT INTO anchors(event_id,session_id,market_duration,
                    anchor_market_slug,anchor_condition_id,anchor_token_up,anchor_token_down,first_side,
                    event_ts_ms,received_ts_ms,available_ts_ms,expiry_ts_ms,features_json,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'OPEN')''',
                    (eid,self.store.session_id,identity.market_duration,identity.market_slug,identity.condition_id,
                     identity.token_up,identity.token_down,side,snapshot.get('event_ts_ms'),received,available,
                     identity.expiry_ts_ms,self.store.pack({'btc':features,'book':snapshot})))
                self.anchors[identity.key].append(cur.lastrowid)
            self.last_anchor[identity.key] = available
        return eid

    def attempt_hedge(self, anchor_id, event_id, snapshot, side, *, min_delay_ms=0, max_delay_ms=None):
        """Identity audit API; no pair cost/PnL computed, no automatic fixed-delay hedge."""
        self.store.db.row_factory = __import__('sqlite3').Row
        anchor = self.store.db.execute('SELECT * FROM anchors WHERE anchor_id=?',(anchor_id,)).fetchone()
        self.store.db.row_factory = None
        if anchor is None:
            raise KeyError(anchor_id)
        ts = snapshot['received_ts_ms']
        expected = anchor['anchor_token_down'] if anchor['first_side']=='UP' else anchor['anchor_token_up']
        token = (snapshot.get(side.lower()) or {}).get('token_id')
        same = (anchor['anchor_market_slug']==snapshot.get('market_slug') and
                anchor['anchor_condition_id']==snapshot.get('condition_id') and expected==token and
                anchor['anchor_token_up']==snapshot.get('token_up') and
                anchor['anchor_token_down']==snapshot.get('token_down'))
        reason = 'ACCEPT' if same else 'CROSS_MARKET_REJECT'
        delta = ts-anchor['received_ts_ms']
        if same and (anchor['status'] != 'OPEN' or ts >= anchor['expiry_ts_ms']):
            reason = 'CLOSED_OR_EXPIRED'
        elif same and (delta < min_delay_ms or (max_delay_ms is not None and delta > max_delay_ms)):
            reason = 'OUTSIDE_WINDOW'
        if reason=='ACCEPT':
            assert anchor['anchor_market_slug']==snapshot['market_slug']
            assert anchor['anchor_condition_id']==snapshot['condition_id'] and expected==token
        self.store.db.execute('INSERT INTO hedge_attempts VALUES(NULL,?,?,?,?,?,?,?,?)',
                              (anchor_id,event_id,snapshot.get('market_slug'),snapshot.get('condition_id'),token,
                               ts,'ACCEPT' if reason=='ACCEPT' else 'REJECT',reason))
        return reason
