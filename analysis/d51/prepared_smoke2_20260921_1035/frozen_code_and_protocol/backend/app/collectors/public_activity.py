import json
import ssl
import time
import random
from urllib.error import HTTPError
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


DATA_API = 'https://data-api.polymarket.com/activity'
PROFILE_API = 'https://gamma-api.polymarket.com/public-profile'


@dataclass(frozen=True)
class BenchmarkWallet:
    name: str
    address: str


def normalize_activity(row: Dict[str, Any], benchmark: str) -> Dict[str, Any]:
    """Keep a stable, analysis-friendly representation of public activity."""
    timestamp = int(row.get('timestamp') or 0)
    size = float(row.get('size') or 0)
    price = float(row.get('price') or 0)
    return {
        'benchmark': benchmark,
        'wallet': row.get('proxyWallet'),
        'timestamp': timestamp,
        'condition_id': row.get('conditionId'),
        'type': str(row.get('type') or ''),
        'side': str(row.get('side') or ''),
        'outcome': row.get('outcome') or '',
        'outcome_index': row.get('outcomeIndex'),
        'asset': row.get('asset') or '',
        'size': size,
        'price': price,
        'usdc_size': float(row.get('usdcSize') or size * price),
        'transaction_hash': row.get('transactionHash') or '',
        'title': row.get('title') or '',
        'slug': row.get('slug') or '',
        'event_slug': row.get('eventSlug') or '',
        'is_combo': bool(row.get('isCombo', False)),
        'raw_json': json.dumps(row, separators=(',', ':'), sort_keys=True),
    }


class PublicActivityCollector:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.context = ssl._create_unverified_context()

    def _request(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        request = urllib.request.Request(
            f'{DATA_API}?{query}',
            headers={'Accept': 'application/json', 'User-Agent': 'PolyQuantLab/1.0'},
        )
        for attempt in range(8):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout, context=self.context) as response:
                    payload = json.loads(response.read().decode('utf-8', 'ignore'))
                break
            except HTTPError as exc:
                if exc.code != 429 or attempt == 7:
                    raise
                retry_after = exc.headers.get('Retry-After')
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = min(60.0, 2.0 ** attempt) + random.random()
                print(f'Polymarket API rate limit; retrying in {delay:.1f}s', flush=True)
                time.sleep(delay)
        if not isinstance(payload, list):
            raise RuntimeError(f'Unexpected Data API response: {payload!r}')
        return payload

    def get_public_profile(self, address: str) -> Dict[str, Any]:
        query = urllib.parse.urlencode({'address': address})
        request = urllib.request.Request(
            f'{PROFILE_API}?{query}',
            headers={'Accept': 'application/json', 'User-Agent': 'PolyQuantLab/1.0'},
        )
        with urllib.request.urlopen(request, timeout=self.timeout, context=self.context) as response:
            payload = json.loads(response.read().decode('utf-8', 'ignore'))
        if not isinstance(payload, dict):
            raise RuntimeError(f'Unexpected profile response for {address}')
        return payload

    def validate_wallet(self, wallet: BenchmarkWallet) -> Dict[str, Any]:
        profile = self.get_public_profile(wallet.address)
        if str(profile.get('name') or '').casefold() != wallet.name.casefold():
            raise ValueError(
                f'{wallet.name} does not match profile name {profile.get("name")!r} at {wallet.address}'
            )
        sample = [normalize_activity(row, wallet.name) for row in self._request({
            'user': wallet.address, 'type': 'TRADE', 'limit': 10, 'offset': 0,
            'sortBy': 'TIMESTAMP', 'sortDirection': 'DESC',
        })]
        required = ('timestamp', 'side', 'outcome', 'price', 'size', 'condition_id')
        for row in sample:
            if not row['timestamp'] or row['side'] not in {'BUY', 'SELL'} or not row['outcome'] or row['price'] < 0 or row['size'] < 0 or not row['condition_id']:
                raise ValueError(f'Invalid trade sample for {wallet.name}: {row}')
        return {'profile': profile, 'sample': sample}

    def fetch_window(self, address: str, start: int = 1, end: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all trades in a time window, splitting before the API offset cap."""
        limit = 500
        rows: List[Dict[str, Any]] = []
        offset = 0
        while True:
            page = self._request({
                'user': address, 'type': 'TRADE', 'limit': limit, 'offset': offset,
                'start': start, 'end': end, 'sortBy': 'TIMESTAMP', 'sortDirection': 'ASC',
            })
            rows.extend(page)
            if len(page) < limit:
                return rows
            offset += limit
            if offset >= 5000:
                if not rows:
                    return rows
                timestamps = [int(row.get('timestamp') or 0) for row in rows]
                midpoint = (min(timestamps) + max(timestamps)) // 2
                if end is not None and midpoint >= end:
                    raise RuntimeError(f'Cannot split dense activity window for {address}')
                left = self.fetch_window(address, start, midpoint)
                right = self.fetch_window(address, midpoint + 1, end)
                return left + right

    def iter_window_pages(self, address: str, start: int, end: int, limit: int = 500):
        """Yield one API page at a time; never materialize a complete window."""
        offset = 0
        cursor = start
        while cursor <= end:
            page = self._request({
                'user': address, 'type': 'TRADE', 'limit': limit, 'offset': offset,
                'start': cursor, 'end': end, 'sortBy': 'TIMESTAMP', 'sortDirection': 'ASC',
            })
            if not page:
                return
            yield page
            last_timestamp = max(int(row.get('timestamp') or cursor) for row in page)
            if len(page) < limit:
                return
            if offset + limit >= 5000:
                yield from self.iter_window_pages(address, last_timestamp, end, limit)
                return
            offset += limit

    def fetch_all(self, wallet: BenchmarkWallet, window_days: int = 30) -> List[Dict[str, Any]]:
        """Fetch maximum history in parallel bounded windows and deduplicate it."""
        oldest = self._request({
            'user': wallet.address, 'type': 'TRADE', 'limit': 1, 'offset': 0,
            'start': 1, 'sortBy': 'TIMESTAMP', 'sortDirection': 'ASC',
        })
        if not oldest:
            return []
        cursor = int(oldest[0].get('timestamp') or 1)
        end_time = int(time.time())
        rows: List[Dict[str, Any]] = []
        window_seconds = window_days * 24 * 60 * 60
        windows = []
        while cursor <= end_time:
            window_end = min(cursor + window_seconds - 1, end_time)
            windows.append((cursor, window_end))
            cursor = window_end + 1
        with ThreadPoolExecutor(max_workers=min(8, len(windows))) as executor:
            futures = [executor.submit(self.fetch_window, wallet.address, start, end) for start, end in windows]
            for future in futures:
                rows.extend(future.result())
        deduplicated = {}
        for row in rows:
            key = (row.get('transactionHash'), row.get('timestamp'), row.get('asset'), row.get('side'), row.get('size'), row.get('price'))
            deduplicated[key] = row
        return [normalize_activity(row, wallet.name) for row in deduplicated.values()]


def reconstruct_inventory(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rebuild per-wallet/per-market outcome inventory from public trades."""
    inventory = defaultdict(float)
    result = []
    for row in sorted(rows, key=lambda item: (item['benchmark'], item['condition_id'] or '', item['timestamp'])):
        if row['type'] != 'TRADE' or not row['condition_id']:
            continue
        sign = 1 if row['side'] == 'BUY' else -1
        key = (row['benchmark'], row['condition_id'], row['outcome'] or row['asset'])
        inventory[key] += sign * row['size']
        result.append({
            'benchmark': row['benchmark'],
            'condition_id': row['condition_id'],
            'outcome': row['outcome'],
            'timestamp': row['timestamp'],
            'side': row['side'],
            'size': row['size'],
            'price': row['price'],
            'inventory': inventory[key],
        })
    return result