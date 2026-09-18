import asyncio
import json
import time
from typing import Any, Dict, Optional

import websockets


class PolymarketOrderbookCollector:
    """Public order-book collector for Polymarket market snapshots and quotes."""

    def __init__(self, market_key: str, token_ids: Dict[str, str], on_quote, expiry_ts_ms: Optional[int] = None):
        self.market_key = market_key
        self.token_ids = token_ids
        self.on_quote = on_quote
        self.expiry_ts_ms = expiry_ts_ms
        self.url = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
        self._books: Dict[str, Dict[str, list]] = {}
        self._expected_tokens = {str(token) for token in token_ids.values()}

    @staticmethod
    def _levels(value: Any) -> list:
        if not isinstance(value, list):
            return []
        levels = []
        for level in value:
            if not isinstance(level, dict):
                continue
            price = level.get('price', level.get('p'))
            quantity = level.get('size', level.get('quantity', level.get('q')))
            try:
                levels.append((float(price), float(quantity)))
            except (TypeError, ValueError):
                continue
        return levels

    def _update_book(self, asset_id: str, bids: list, asks: list) -> None:
        if asset_id not in self._expected_tokens:
            print(f'STALE_TOKEN_EVENT_IGNORED ({self.market_key}): {asset_id}')
            return
        self._books[asset_id] = {'bids': self._levels(bids), 'asks': self._levels(asks)}

    def _apply_price_changes(self, payload: Dict[str, Any]) -> None:
        for change in payload.get('price_changes', []):
            asset_id = str(change.get('asset_id', ''))
            if not asset_id:
                continue
            if asset_id not in self._expected_tokens:
                print(f'STALE_TOKEN_EVENT_IGNORED ({self.market_key}): {asset_id}')
                continue
            book = self._books.setdefault(asset_id, {'bids': [], 'asks': []})
            side = 'bids' if str(change.get('side', '')).upper() == 'BUY' else 'asks'
            levels = {price: size for price, size in book[side]}
            try:
                price = float(change['price'])
                size = float(change['size'])
            except (KeyError, TypeError, ValueError):
                continue
            if size <= 0:
                levels.pop(price, None)
            else:
                levels[price] = size
            book[side] = sorted(levels.items())

    def normalize_snapshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a CLOB book event into one control snapshot."""
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get('bids') is not None:
                    self._update_book(str(item.get('asset_id', '')), item.get('bids'), item.get('asks'))
            payload = next((item for item in payload if isinstance(item, dict)), {})
        elif payload.get('event_type') == 'price_change':
            self._apply_price_changes(payload)

        event_ts_ms = payload.get('timestamp', payload.get('event_ts_ms', payload.get('ts')))
        try:
            event_ts_ms = int(event_ts_ms) if event_ts_ms is not None else None
        except (TypeError, ValueError):
            event_ts_ms = None
        expiry_ts_ms = payload.get('end_date_ts', payload.get('expiry_ts_ms')) or self.expiry_ts_ms
        try:
            expiry_ts_ms = int(expiry_ts_ms) if expiry_ts_ms is not None else None
        except (TypeError, ValueError):
            expiry_ts_ms = None

        outcomes = payload.get('outcomes') or {}
        if isinstance(outcomes, list):
            outcomes = {str(item.get('token_id')): item for item in outcomes if isinstance(item, dict)}
        if not isinstance(outcomes, dict):
            outcomes = {}

        now_ms = int(time.time() * 1000)
        asset_id = str(payload.get('asset_id', payload.get('token_id', '')))
        if asset_id and asset_id not in self._expected_tokens:
            print(f'STALE_TOKEN_EVENT_IGNORED ({self.market_key}): {asset_id}')
            return {
                'market_key': self.market_key,
                'token_ids': self.token_ids,
                'event_ts_ms': event_ts_ms,
                'recv_ts_ms': now_ms,
                'expiry_ts_ms': expiry_ts_ms,
                'time_remaining_ms': max(0, expiry_ts_ms - now_ms) if expiry_ts_ms else None,
                'stale_token': True,
            }
        if asset_id and ('bids' in payload or 'asks' in payload):
            self._update_book(asset_id, payload.get('bids'), payload.get('asks'))
        values = {}
        for outcome, token_id in self.token_ids.items():
            token = str(token_id)
            details = outcomes.get(token, {})
            book = self._books.get(token, {'bids': [], 'asks': []})
            bids = self._levels(details.get('bids')) if isinstance(details, dict) and details.get('bids') else book['bids']
            asks = self._levels(details.get('asks')) if isinstance(details, dict) and details.get('asks') else book['asks']
            bid = details.get('best_bid') if isinstance(details, dict) else None
            ask = details.get('best_ask') if isinstance(details, dict) else None
            bid_qty = details.get('bid_quantity', 0.0) if isinstance(details, dict) else 0.0
            ask_qty = details.get('ask_quantity', 0.0) if isinstance(details, dict) else 0.0
            if bids:
                bid, bid_qty = max(bids, key=lambda level: level[0])
            if asks:
                ask, ask_qty = min(asks, key=lambda level: level[0])
            values[outcome.lower()] = {
                'token_id': token,
                'bid': float(bid) if bid is not None else None,
                'ask': float(ask) if ask is not None else None,
                'bid_qty': float(bid_qty or 0),
                'ask_qty': float(ask_qty or 0),
            }
        return {
            'market_key': self.market_key,
            'token_ids': self.token_ids,
            'event_ts_ms': event_ts_ms,
            'recv_ts_ms': now_ms,
            'expiry_ts_ms': expiry_ts_ms,
            'time_remaining_ms': max(0, expiry_ts_ms - now_ms) if expiry_ts_ms else None,
            **values,
        }

    async def run(self):
        reconnect_delay = 1
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as ws:
                    reconnect_delay = 1
                    print(f'Polymarket WS: CONNECTED ({self.market_key})')
                    msg = json.dumps({'assets_ids': list(self.token_ids.values()), 'type': 'market'})
                    await ws.send(msg)
                    while True:
                        timeout = None
                        if self.expiry_ts_ms is not None:
                            remaining_ms = self.expiry_ts_ms - int(time.time() * 1000)
                            if remaining_ms <= 0:
                                print(f'Polymarket WS: EXPIRED ({self.market_key})')
                                return
                            timeout = max(0.1, remaining_ms / 1000)
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            print(f'Polymarket WS: EXPIRED ({self.market_key})')
                            return
                        recv_ts_ms = int(time.time() * 1000)
                        if not raw or raw == '0':
                            continue
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            continue
                        if isinstance(payload, (dict, list)):
                            snapshot = self.normalize_snapshot(payload)
                            snapshot['recv_ts_ms'] = recv_ts_ms
                            await self.on_quote(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f'[polymarket:{self.market_key}] reconnect after error: {exc}')
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30)
