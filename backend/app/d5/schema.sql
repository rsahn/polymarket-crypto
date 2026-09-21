PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_info(version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO schema_info VALUES(1);
CREATE TABLE IF NOT EXISTS sessions(
 session_id TEXT PRIMARY KEY, started_at_ms INTEGER NOT NULL, ended_at_ms INTEGER,
 code_version TEXT NOT NULL, schema_version INTEGER NOT NULL CHECK(schema_version=1),
 mode TEXT NOT NULL CHECK(mode='SHADOW'), status TEXT NOT NULL, config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS markets(
 condition_id TEXT NOT NULL, market_slug TEXT NOT NULL, market_duration TEXT NOT NULL,
 token_up TEXT NOT NULL, token_down TEXT NOT NULL, expiry_ts_ms INTEGER NOT NULL,
 metadata_json TEXT NOT NULL,
 PRIMARY KEY(condition_id,market_slug), UNIQUE(market_slug), UNIQUE(condition_id),
 CHECK(market_duration IN ('5m','15m')), CHECK(token_up != token_down),
 CHECK(length(token_up)>0 AND length(token_down)>0)
);
CREATE TABLE IF NOT EXISTS events(
 event_id INTEGER PRIMARY KEY AUTOINCREMENT,
 session_id TEXT NOT NULL REFERENCES sessions(session_id), kind TEXT NOT NULL,
 event_ts_ms INTEGER, received_ts_ms INTEGER NOT NULL, available_ts_ms INTEGER NOT NULL,
 market_duration TEXT, market_slug TEXT, condition_id TEXT, token_up TEXT, token_down TEXT,
 generation INTEGER, payload_json TEXT NOT NULL,
 FOREIGN KEY(condition_id,market_slug) REFERENCES markets(condition_id,market_slug)
);
CREATE INDEX IF NOT EXISTS idx_d5_events_session ON events(session_id,event_id);
CREATE INDEX IF NOT EXISTS idx_d5_events_market ON events(market_slug,event_id);
CREATE TRIGGER IF NOT EXISTS d5_event_identity BEFORE INSERT ON events
WHEN NEW.condition_id IS NOT NULL
BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM markets m WHERE m.condition_id=NEW.condition_id
 AND m.market_slug=NEW.market_slug AND m.token_up=NEW.token_up AND m.token_down=NEW.token_down
 AND m.market_duration=NEW.market_duration) THEN RAISE(ABORT,'CROSS_MARKET_REJECT') END;
END;
CREATE TABLE IF NOT EXISTS book_sides(
 event_id INTEGER NOT NULL REFERENCES events(event_id), side TEXT NOT NULL CHECK(side IN ('UP','DOWN')),
 token_id TEXT NOT NULL, event_ts_ms INTEGER, received_ts_ms INTEGER NOT NULL,
 best_bid REAL, best_ask REAL, best_bid_qty REAL NOT NULL, best_ask_qty REAL NOT NULL,
 spread REAL, bids_json TEXT NOT NULL, asks_json TEXT NOT NULL, source_hash TEXT, sequence TEXT,
 PRIMARY KEY(event_id,side)
);
CREATE TRIGGER IF NOT EXISTS d5_side_identity BEFORE INSERT ON book_sides
BEGIN
 SELECT CASE WHEN NEW.token_id != (SELECT CASE WHEN NEW.side='UP' THEN token_up ELSE token_down END
 FROM events WHERE event_id=NEW.event_id) THEN RAISE(ABORT,'CROSS_MARKET_REJECT') END;
END;
CREATE TABLE IF NOT EXISTS anchors(
 anchor_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL REFERENCES events(event_id),
 session_id TEXT NOT NULL REFERENCES sessions(session_id),
 market_duration TEXT NOT NULL, anchor_market_slug TEXT NOT NULL, anchor_condition_id TEXT NOT NULL,
 anchor_token_up TEXT NOT NULL, anchor_token_down TEXT NOT NULL, first_side TEXT NOT NULL,
 event_ts_ms INTEGER, received_ts_ms INTEGER NOT NULL, available_ts_ms INTEGER NOT NULL,
 expiry_ts_ms INTEGER NOT NULL, features_json TEXT NOT NULL,
 status TEXT NOT NULL, closed_at_ms INTEGER, close_reason TEXT,
 UNIQUE(event_id,first_side), FOREIGN KEY(anchor_condition_id,anchor_market_slug)
 REFERENCES markets(condition_id,market_slug)
);
CREATE TABLE IF NOT EXISTS hedge_attempts(
 attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, anchor_id INTEGER NOT NULL REFERENCES anchors(anchor_id),
 event_id INTEGER NOT NULL REFERENCES events(event_id), hedge_market_slug TEXT,
 hedge_condition_id TEXT, hedge_token_id TEXT, received_ts_ms INTEGER NOT NULL,
 status TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS d5_anchor_identity BEFORE INSERT ON anchors
BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM events e JOIN markets m USING(condition_id,market_slug)
 WHERE e.event_id=NEW.event_id AND e.kind='BOOK' AND e.session_id=NEW.session_id
 AND e.market_slug=NEW.anchor_market_slug AND e.condition_id=NEW.anchor_condition_id
 AND e.token_up=NEW.anchor_token_up AND e.token_down=NEW.anchor_token_down
 AND NEW.available_ts_ms<m.expiry_ts_ms)
 THEN RAISE(ABORT,'CROSS_MARKET_REJECT') END;
END;
CREATE TRIGGER IF NOT EXISTS d5_hedge_identity BEFORE INSERT ON hedge_attempts
WHEN NEW.status='ACCEPT'
BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM anchors a JOIN events e ON e.event_id=NEW.event_id
 WHERE a.anchor_id=NEW.anchor_id AND a.anchor_market_slug=NEW.hedge_market_slug
 AND a.anchor_condition_id=NEW.hedge_condition_id
 AND a.anchor_market_slug=e.market_slug AND a.anchor_condition_id=e.condition_id
 AND NEW.hedge_token_id=CASE WHEN a.first_side='UP' THEN a.anchor_token_down ELSE a.anchor_token_up END)
 THEN RAISE(ABORT,'CROSS_MARKET_REJECT') END;
END;
