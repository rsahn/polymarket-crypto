import json
import re
import ssl
import time
import urllib.request
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PolymarketMarket:
    market_key: str
    slug: str
    token_ids: Dict[str, str]
    active: bool = True
    source: str = 'polymarket'
    expiry_ts_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class PolymarketMarketDiscovery:
    """Discover active BTC Up/Down markets and normalize the token identities."""

    @staticmethod
    def parse_market_list(payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for item in payload:
            q = str(item.get('question', '') or '').lower()
            slug = str(item.get('slug', '') or '').lower()
            if not any(term in f'{slug} {q}' for term in ('btc', 'bitcoin')):
                continue
            text = f'{slug} {q}'
            if not re.search(r'(?<!\d)(5\s*min|5m|five minutes?)(?!\w)', text) and not re.search(r'(?<!\d)(15\s*min|15m|fifteen minutes?)(?!\w)', text):
                continue
            outcomes = item.get('outcomes') or []
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except json.JSONDecodeError:
                    outcomes = []
            clob_ids = item.get('clobTokenIds') or item.get('clob_token_ids') or []
            if isinstance(clob_ids, str):
                try:
                    clob_ids = json.loads(clob_ids)
                except json.JSONDecodeError:
                    clob_ids = []
            if outcomes and isinstance(outcomes[0], str):
                labels = {str(label).lower(): str(token) for label, token in zip(outcomes, clob_ids)}
            else:
                labels = {str(o.get('label', '') or '').lower(): str(o.get('id', '') or '') for o in outcomes if isinstance(o, dict)}
            up_id = labels.get('yes') or labels.get('up')
            down_id = labels.get('no') or labels.get('down')
            if clob_ids and len(clob_ids) >= 2:
                up_id = up_id or str(clob_ids[0])
                down_id = down_id or str(clob_ids[1])
            if not up_id or not down_id:
                continue
            if re.search(r'(?<!\d)(15\s*min|15m|fifteen minutes?)(?!\w)', text):
                market_key = '15m'
            elif re.search(r'(?<!\d)(5\s*min|5m|five minutes?)(?!\w)', text):
                market_key = '5m'
            else:
                continue
            matches.append({
                'market_key': market_key,
                'slug': slug,
                'token_ids': {'UP': up_id, 'DOWN': down_id},
                'active': bool(item.get('active', True)),
                'expiry_ts_ms': PolymarketMarketDiscovery._expiry_ts_ms(item),
                'metadata': item,
            })

        def market_order(item: Dict[str, Any]) -> int:
            key = str(item.get('market_key', ''))
            if key == '5m':
                return 0
            if key == '15m':
                return 1
            return 99

        return sorted(matches, key=market_order)

    @staticmethod
    def _expiry_ts_ms(item: Dict[str, Any]) -> Optional[int]:
        value = item.get('end_date_ts') or item.get('endDate') or item.get('expiry')
        if isinstance(value, (int, float)):
            return int(value if value > 10_000_000_000 else value * 1000)
        if isinstance(value, str):
            try:
                return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000)
            except ValueError:
                return None
        return None

    @staticmethod
    def fetch_active_markets() -> List[Dict[str, Any]]:
        ctx = ssl._create_unverified_context()
        now_s = int(time.time())
        markets = []
        for minutes in (5, 15):
            window_s = minutes * 60
            start_s = now_s - (now_s % window_s)
            for candidate in (start_s, start_s - window_s, start_s + window_s):
                url = f'https://gamma-api.polymarket.com/markets?slug=btc-updown-{minutes}m-{candidate}'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
                try:
                    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                        data = json.loads(resp.read().decode('utf-8', 'ignore'))
                except (OSError, json.JSONDecodeError):
                    continue
                items = data.get('data', []) if isinstance(data, dict) else data
                if isinstance(items, list):
                    markets.extend(items)
                    if items:
                        break
        return PolymarketMarketDiscovery.parse_market_list(markets)

    @staticmethod
    def get_active_btc_markets() -> List[Dict[str, Any]]:
        try:
            markets = PolymarketMarketDiscovery.fetch_active_markets()
        except Exception as exc:
            print(f'[polymarket:discovery] unavailable: {exc}')
            markets = []
        return [m for m in markets if m.get('active') is True and m.get('market_key') in {'5m', '15m'}]
