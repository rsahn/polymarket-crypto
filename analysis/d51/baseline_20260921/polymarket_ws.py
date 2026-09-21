import asyncio
import json
import time
import hashlib
import math
from collections import deque
from contextlib import suppress
from typing import Any, Dict, Optional

import websockets


class PolymarketOrderbookCollector:
    """
    Public Polymarket CLOB order-book collector.

    Resilience rules:
    - reset the local order book on every WebSocket connection/reconnection;
    - require a fresh full `book` snapshot for BOTH expected tokens before
      applying incremental `price_change` events;
    - ignore stale/foreign token events;
    - send Polymarket's application-level `PING` heartbeat every 10 seconds;
    - reconnect if the stream becomes silent even though the socket appears open;
    - never rebuild a post-reconnect book from pre-reconnect state.
    """

    HEARTBEAT_SECONDS = 10.0
    STREAM_IDLE_TIMEOUT_SECONDS = 25.0
    INITIAL_BOOK_TIMEOUT_SECONDS = 4.0
    MAX_RAW_DIAGNOSTICS_PER_CONNECTION = 6

    def __init__(
        self,
        market_key: str,
        token_ids: Dict[str, str],
        on_quote,
        expiry_ts_ms: Optional[int] = None,
        identity=None,
    ):
        self.market_key = market_key
        self.token_ids = token_ids
        self.on_quote = on_quote
        self.expiry_ts_ms = expiry_ts_ms
        self.identity = identity
        self._last_source_ts = {}
        self._source_metadata = {}
        self._wire_seen = deque(maxlen=2048)
        self.url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

        self._expected_tokens = {str(token) for token in token_ids.values()}
        self._books: Dict[str, Dict[str, list]] = {}
        self._initialized_tokens = set()
        self._connection_generation = 0
        self._authoritative_top = {}
        # Keep the monotonically increasing WS generation counter.
        self._raw_messages_seen = 0
        self._last_message_monotonic: Optional[float] = None
        self._authoritative_top: Dict[str, Dict[str, Optional[float]]] = {}

    def _reset_connection_state(self) -> None:
        """Hard reset: never reuse order-book state across WS generations."""
        self._books = {}
        self._authoritative_top = {}
        self._last_source_ts = {}
        self._source_metadata = {}
        self._wire_seen.clear()
        self._initialized_tokens = set()
        self._raw_messages_seen = 0
        self._last_message_monotonic: Optional[float] = None

    @staticmethod
    def _levels(value: Any) -> list:
        if not isinstance(value, list):
            return []

        levels = []
        for level in value:
            if not isinstance(level, dict):
                continue

            price = level.get("price", level.get("p"))
            quantity = level.get(
                "size",
                level.get("quantity", level.get("q")),
            )

            try:
                price_f = float(price)
                quantity_f = float(quantity)
            except (TypeError, ValueError):
                continue

            if math.isfinite(quantity_f) and math.isfinite(price_f) and quantity_f > 0 and 0 <= price_f <= 1:
                levels.append((price_f, quantity_f))

        return levels

    def _update_book(self, asset_id: str, bids: list, asks: list) -> bool:
        asset_id = str(asset_id)

        if asset_id not in self._expected_tokens:
            print(
                f"STALE_TOKEN_EVENT_IGNORED "
                f"({self.market_key}): {asset_id}"
            )
            return False

        # A `book` event is authoritative: replace both sides completely.
        self._books[asset_id] = {
            "bids": self._levels(bids),
            "asks": self._levels(asks),
        }
        self._authoritative_top.pop(asset_id, None)
        self._initialized_tokens.add(asset_id)
        return True

    def _apply_price_changes(self, payload: Dict[str, Any]) -> None:
        """
        Apply deltas only to tokens that already received a fresh full book
        snapshot during THIS WebSocket connection.

        This prevents a reconnect from creating a synthetic partial book.
        """
        changes = payload.get("price_changes", payload.get("priceChanges", []))
        if not isinstance(changes, list):
            return

        for change in changes:
            if not isinstance(change, dict):
                continue

            asset_id = str(
                change.get(
                    "asset_id",
                    change.get("token_id", change.get("tokenId", "")),
                )
            )
            if not asset_id:
                continue

            if asset_id not in self._expected_tokens:
                print(
                    f"STALE_TOKEN_EVENT_IGNORED "
                    f"({self.market_key}): {asset_id}"
                )
                continue

            # Critical recovery rule: deltas are meaningless until a fresh
            # authoritative book for that token has arrived after reconnect.
            if asset_id not in self._initialized_tokens:
                continue

            book = self._books.get(asset_id)
            if not book:
                continue

            side_raw = str(change.get("side", "")).upper()
            if side_raw == "BUY":
                side = "bids"
            elif side_raw == "SELL":
                side = "asks"
            else:
                continue

            try:
                price = float(change["price"])
                size = float(change["size"])
            except (KeyError, TypeError, ValueError):
                continue

            levels = {price_: size_ for price_, size_ in book[side]}

            if size <= 0:
                levels.pop(price, None)
            else:
                levels[price] = size

            book[side] = list(levels.items())

            # price_change carries Polymarket's own best bid/ask. Keep it as an
            # authoritative top-of-book hint and compare it with our rebuilt book.
            best_bid_raw = change.get("best_bid", change.get("bestBid"))
            best_ask_raw = change.get("best_ask", change.get("bestAsk"))
            try:
                best_bid_raw = float(best_bid_raw) if best_bid_raw is not None else None
            except (TypeError, ValueError):
                best_bid_raw = None
            try:
                best_ask_raw = float(best_ask_raw) if best_ask_raw is not None else None
            except (TypeError, ValueError):
                best_ask_raw = None

            if best_bid_raw is not None or best_ask_raw is not None:
                self._authoritative_top[asset_id] = {
                    "bid": best_bid_raw,
                    "ask": best_ask_raw,
                }

                local_bids = book.get("bids", [])
                local_asks = book.get("asks", [])
                local_bid = max(local_bids, key=lambda x: x[0])[0] if local_bids else None
                local_ask = min(local_asks, key=lambda x: x[0])[0] if local_asks else None

                # V5: Polymarket-provided BBO is authoritative.
                # Local depth is retained only for quantity/depth context.

    @staticmethod
    def _unwrap_event(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Support both the raw CLOB schema (`event_type`, `asset_id`, ...)
        and the newer topic/type/payload envelope if it is ever returned.
        """
        if not isinstance(payload, dict):
            return {}

        inner = payload.get("payload")
        if (
            isinstance(inner, dict)
            and payload.get("topic") == "market"
            and payload.get("type")
        ):
            event = dict(inner)
            event.setdefault("event_type", payload.get("type"))

            # Preserve an outer timestamp if the inner payload omitted it.
            if "timestamp" not in event and payload.get("timestamp") is not None:
                event["timestamp"] = payload.get("timestamp")

            return event

        return payload

    def _process_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        event = self._unwrap_event(raw_event)
        event_type = str(
            event.get("event_type", event.get("type", ""))
        ).lower()

        # Accept both legacy and SDK naming variants.
        asset_id = str(
            event.get(
                "asset_id",
                event.get("token_id", event.get("tokenId", "")),
            )
        )

        if asset_id and asset_id not in self._expected_tokens:
            print(
                f"STALE_TOKEN_EVENT_IGNORED "
                f"({self.market_key}): {asset_id}"
            )
            return event

        if event_type == "book" or (
            asset_id and ("bids" in event or "asks" in event)
        ):
            self._update_book(
                asset_id,
                event.get("bids", []),
                event.get("asks", []),
            )

        elif event_type == "price_change":
            self._apply_price_changes(event)

        return event

    def normalize_snapshot(self, payload: Any, received_ts_ms=None) -> Dict[str, Any]:
        """
        Normalize one WS message into a control snapshot.

        A list may contain the initial full books for both tokens. Process the
        whole list BEFORE building the normalized snapshot.
        """
        events = payload if isinstance(payload, list) else [payload]
        processed_events = []

        # Fence the entire message BEFORE mutating either token's book.
        wire_digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        reject = 'DUPLICATE_EVENT' if wire_digest in self._wire_seen else None
        updates = []
        for raw in events:
            if not isinstance(raw, dict):
                continue
            event = self._unwrap_event(raw)
            if self.identity and str(event.get('market','')).startswith('0x') and event['market'] != self.identity.condition_id:
                reject = 'CROSS_MARKET_REJECT'
            changes = event.get('price_changes', event.get('priceChanges', []))
            tokens = [str(c.get('asset_id', c.get('token_id', c.get('tokenId','')))) for c in changes]
            token = event.get('asset_id', event.get('token_id',event.get('tokenId')))
            if token:
                tokens.append(str(token))
            if any(t not in self._expected_tokens for t in tokens):
                reject = 'CROSS_MARKET_REJECT'
            source_ts = event.get('timestamp', event.get('event_ts_ms'))
            try:
                source_ts = int(source_ts) if source_ts is not None else None
            except (TypeError, ValueError):
                reject = 'INVALID_EVENT_TIMESTAMP'
                source_ts = None
            for t in tokens:
                if source_ts is not None and source_ts < self._last_source_ts.get(t, -1):
                    reject = 'OUT_OF_ORDER'
                if changes or 'bids' in event or 'asks' in event:
                    change = next((c for c in changes if str(c.get('asset_id',c.get('token_id',c.get('tokenId',''))))==t), {})
                    updates.append((t, source_ts, change.get('hash',event.get('hash')), event.get('sequence')))
        if reject:
            return {'market_key': self.market_key, 'token_ids': dict(self.token_ids),
                    'recv_ts_ms': time.time_ns()//1_000_000, 'reject_reason': reject,
                    'stale_token': reject == 'CROSS_MARKET_REJECT', 'wire_hash': wire_digest,
                    **(self.identity.fields() if self.identity else {})}
        self._wire_seen.append(wire_digest)
        for token, ts, source_hash, sequence in updates:
            if ts is not None:
                self._last_source_ts[token] = ts
            self._source_metadata[token] = {'event_ts_ms': ts, 'source_hash': source_hash,
                                            'sequence': sequence,
                                            'received_ts_ms': received_ts_ms or time.time_ns()//1_000_000}

        for item in events:
            if isinstance(item, dict):
                processed_events.append(self._process_event(item))

        # Use the latest processed event for timing metadata.
        meta = processed_events[-1] if processed_events else {}

        event_ts_ms = meta.get(
            "timestamp",
            meta.get("event_ts_ms", meta.get("ts")),
        )
        try:
            event_ts_ms = (
                int(event_ts_ms)
                if event_ts_ms is not None
                else None
            )
        except (TypeError, ValueError):
            event_ts_ms = None

        expiry_ts_ms = (
            meta.get("end_date_ts", meta.get("expiry_ts_ms"))
            or self.expiry_ts_ms
        )
        try:
            expiry_ts_ms = (
                int(expiry_ts_ms)
                if expiry_ts_ms is not None
                else None
            )
        except (TypeError, ValueError):
            expiry_ts_ms = None

        now_ms = int(time.time() * 1000)
        values = {}

        for outcome, token_id in self.token_ids.items():
            token = str(token_id)
            book = self._books.get(token)

            # Until a fresh authoritative book has arrived for this token,
            # expose no bid/ask. main.py will remain WAITING_BOOK.
            if (
                token not in self._initialized_tokens
                or not book
            ):
                values[outcome.lower()] = {
                    "token_id": token,
                    "bid": None,
                    "ask": None,
                    "bid_qty": 0.0,
                    "ask_qty": 0.0,
                }
                continue

            bids = book.get("bids", [])
            asks = book.get("asks", [])

            bid = None
            ask = None
            bid_qty = 0.0
            ask_qty = 0.0

            if bids:
                bid, bid_qty = max(
                    bids,
                    key=lambda level: level[0],
                )

            if asks:
                ask, ask_qty = min(
                    asks,
                    key=lambda level: level[0],
                )

            # If Polymarket supplied best_bid/best_ask on a price_change, use
            # those prices as authoritative. Quantity is accepted only when the
            # corresponding price exists in our local depth; otherwise expose 0.
            top = self._authoritative_top.get(token) or {}
            auth_bid = top.get("bid")
            auth_ask = top.get("ask")

            if auth_bid is not None:
                bid = auth_bid
                bid_qty = next((q for p, q in bids if p == auth_bid), 0.0)
            if auth_ask is not None:
                ask = auth_ask
                ask_qty = next((q for p, q in asks if p == auth_ask), 0.0)

            values[outcome.lower()] = {
                "token_id": token,
                "bid": float(bid) if bid is not None else None,
                "ask": float(ask) if ask is not None else None,
                "bid_qty": float(bid_qty or 0.0),
                "ask_qty": float(ask_qty or 0.0),
                "bids": sorted([(p,q) for p,q in bids if bid is not None and p <= bid], reverse=True)[:20],
                "asks": sorted([(p,q) for p,q in asks if ask is not None and p >= ask])[:20],
                **self._source_metadata.get(token, {}),
            }

        return {
            "market_key": self.market_key,
            "market_duration": self.market_key,
            **(self.identity.fields() if self.identity else {}),
            "token_ids": self.token_ids,
            "event_ts_ms": event_ts_ms,
            "recv_ts_ms": now_ms,
            "received_ts_ms": now_ms,
            "wire_hash": wire_digest,
            "connection_generation": self._connection_generation,
            "source_metadata": [{k:v for k,v in event.items() if k not in ('bids','asks','price_changes','priceChanges')}
                                for event in processed_events],
            "expiry_ts_ms": expiry_ts_ms,
            "time_remaining_ms": (
                max(0, expiry_ts_ms - now_ms)
                if expiry_ts_ms
                else None
            ),
            "book_generation_ready": (
                self._initialized_tokens == self._expected_tokens
            ),
            "bbo_source": "polymarket_price_change"
                if self._authoritative_top
                else "full_book",
            **values,
        }

    def _diagnose_raw_message(self, raw: Any) -> None:
        """Print only the first few messages of each WS generation."""
        if self._raw_messages_seen >= self.MAX_RAW_DIAGNOSTICS_PER_CONNECTION:
            return

        self._raw_messages_seen += 1

        if isinstance(raw, bytes):
            try:
                preview = raw.decode("utf-8", errors="replace")
            except Exception:
                preview = repr(raw)
        else:
            preview = str(raw)

        preview = preview.replace("\n", " ")[:500]
        print(
            f"POLY_RAW ({self.market_key}) "
            f"gen={self._connection_generation} "
            f"msg={self._raw_messages_seen}: {preview}"
        )

    def _book_ready(self) -> bool:
        return self._initialized_tokens == self._expected_tokens

    def _initialized_summary(self) -> str:
        return f"{len(self._initialized_tokens)}/{len(self._expected_tokens)}"

    async def _heartbeat(self, ws) -> None:
        """
        Polymarket's market WS requires an application-level text PING every
        10 seconds. This is separate from RFC WebSocket ping frames.
        """
        while True:
            await asyncio.sleep(self.HEARTBEAT_SECONDS)
            await ws.send("PING")

    async def run(self):
        """
        Run exactly one WS generation at a time.

        Important: this collector does NOT silently reconnect forever inside a
        single task anymore. If a connection fails, never produces the two
        authoritative initial books, or becomes idle, the exception is allowed
        to escape to main.py. The V6 supervisor then creates a brand-new
        collector task/generation.

        This removes the previous double-reconnect loop:
            collector.run() reconnects internally
            + main.py also restarts collector.run()
        which could leave CONNECTED sockets with no usable initial book.
        """
        heartbeat_task = None
        self._connection_generation += 1
        generation = self._connection_generation
        self._reset_connection_state()

        try:
            async with websockets.connect(
                self.url,
                ping_interval=None,
                close_timeout=2,
                open_timeout=10,
            ) as ws:
                print(
                    f"Polymarket WS: CONNECTED ({self.market_key}) "
                    f"gen={generation}"
                )

                subscription = {
                    "assets_ids": [
                        str(token)
                        for token in self.token_ids.values()
                    ],
                    "type": "market",
                }
                encoded_subscription = json.dumps(subscription)

                print(
                    f"POLY_SUBSCRIBE ({self.market_key}) "
                    f"gen={generation} "
                    f"tokens={subscription['assets_ids']}"
                )
                await ws.send(encoded_subscription)

                heartbeat_task = asyncio.create_task(
                    self._heartbeat(ws),
                    name=f"{self.market_key}-polymarket-heartbeat",
                )

                # A new subscription must yield authoritative book snapshots.
                initial_deadline = (
                    time.monotonic()
                    + self.INITIAL_BOOK_TIMEOUT_SECONDS
                )

                while True:
                    now_ms = int(time.time() * 1000)

                    if self.expiry_ts_ms is not None:
                        remaining_ms = self.expiry_ts_ms - now_ms
                        if remaining_ms <= 0:
                            print(
                                f"Polymarket WS: EXPIRED "
                                f"({self.market_key})"
                            )
                            return
                    else:
                        remaining_ms = None

                    # Before the first complete book, use a short watchdog.
                    if not self._book_ready():
                        remaining_initial = (
                            initial_deadline - time.monotonic()
                        )
                        if remaining_initial <= 0:
                            raise ConnectionError(
                                "initial book timeout "
                                f"initialized={self._initialized_summary()}"
                            )
                        recv_timeout = remaining_initial
                    else:
                        recv_timeout = self.STREAM_IDLE_TIMEOUT_SECONDS

                    if remaining_ms is not None:
                        recv_timeout = min(
                            recv_timeout,
                            max(0.1, remaining_ms / 1000),
                        )

                    try:
                        raw = await asyncio.wait_for(
                            ws.recv(),
                            timeout=recv_timeout,
                        )
                    except asyncio.TimeoutError:
                        now_ms = int(time.time() * 1000)

                        if (
                            self.expiry_ts_ms is not None
                            and now_ms >= self.expiry_ts_ms
                        ):
                            print(
                                f"Polymarket WS: EXPIRED "
                                f"({self.market_key})"
                            )
                            return

                        if not self._book_ready():
                            raise ConnectionError(
                                "initial book timeout "
                                f"initialized={self._initialized_summary()}"
                            )

                        raise ConnectionError(
                            "market stream idle timeout"
                        )

                    recv_ts_ms = int(time.time() * 1000)
                    self._last_message_monotonic = time.monotonic()

                    if not raw:
                        continue

                    self._diagnose_raw_message(raw)

                    if isinstance(raw, bytes):
                        try:
                            raw = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            continue

                    # Heartbeat / non-JSON service messages.
                    if raw in ("0", "PONG", "pong"):
                        continue

                    try:
                        payload = json.loads(raw)
                    except (TypeError, json.JSONDecodeError):
                        # Keep the diagnostic above; do not treat arbitrary
                        # service text as an order-book event.
                        continue

                    if not isinstance(payload, (dict, list)):
                        continue

                    was_ready = self._book_ready()

                    snapshot = self.normalize_snapshot(payload, recv_ts_ms)
                    snapshot["recv_ts_ms"] = recv_ts_ms
                    snapshot["received_ts_ms"] = recv_ts_ms

                    if not was_ready and self._book_ready():
                        print(
                            f"POLY_BOOK_SYNCED ({self.market_key}) "
                            f"gen={generation} "
                            f"initialized={self._initialized_summary()}"
                        )

                    await self.on_quote(snapshot)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            self._reset_connection_state()
            print(
                f"[polymarket:{self.market_key}] "
                f"connection generation failed "
                f"gen={generation}: {exc}"
            )
            # Let main.py V6 own retry/backoff/generation fencing.
            raise

        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task

