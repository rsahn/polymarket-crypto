import json
import datetime
import re
import random
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'analysis_bonereaper_snapshot.db'
CACHE = ROOT / 'analysis' / 'bonereaper' / 'market_metadata.json'
ENDPOINT = 'https://gamma-api.polymarket.com/markets/slug/'
BULK_ENDPOINT = 'https://gamma-api.polymarket.com/markets'


def fetch(slug):
    request = urllib.request.Request(ENDPOINT + urllib.request.quote(slug, safe=''), headers={'Accept': 'application/json', 'User-Agent': 'PolyQuantLab/1.0'})
    for attempt in range(7):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode('utf-8', 'ignore'))
            return {
                'slug': slug,
                'condition_id': payload.get('conditionId'),
                'title': payload.get('question'),
                'start_time': payload.get('startDate'),
                'expiry_time': payload.get('endDate'),
                'closed': payload.get('closed'),
                'active': payload.get('active'),
                'resolved_by': payload.get('resolvedBy'),
                'uma_resolution_statuses': payload.get('umaResolutionStatuses'),
                'outcomes': payload.get('outcomes'),
                'outcome_prices': payload.get('outcomePrices'),
                'resolution_source': payload.get('resolutionSource'),
                'status': 'FOUND',
            }
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {'slug': slug, 'status': 'NOT_FOUND'}
            if exc.code != 429 or attempt == 6:
                return {'slug': slug, 'status': f'HTTP_{exc.code}'}
            time.sleep(min(60, 2 ** attempt) + random.random())
        except Exception as exc:
            if attempt == 6:
                return {'slug': slug, 'status': f'ERROR_{type(exc).__name__}'}
            time.sleep(1 + random.random())


def fetch_page(offset, limit=100):
    query = urllib.parse.urlencode({'limit': limit, 'offset': offset})
    request = urllib.request.Request(BULK_ENDPOINT + '?' + query, headers={'Accept': 'application/json', 'User-Agent': 'PolyQuantLab/1.0'})
    for attempt in range(7):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode('utf-8', 'ignore'))
            return payload if isinstance(payload, list) else []
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 6:
                raise
            time.sleep(min(60, 2 ** attempt) + random.random())


def main():
    cache = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
    conn = sqlite3.connect(f'file:{SNAPSHOT}?mode=ro', uri=True)
    slugs = [row[0] for row in conn.execute("select distinct slug from benchmark_activity where benchmark='Bonereaper' and slug is not null and slug != ''")]
    conn.close()
    slug_set = set(slugs)
    pending = slug_set - set(cache)
    print(f'known={len(slugs)} cached={len(cache)} pending={len(pending)}', flush=True)
    offset = 0
    while pending:
        try:
            page = fetch_page(offset)
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                break
            raise
        if not page:
            break
        for item in page:
            slug = item.get('slug')
            if slug not in pending:
                continue
            cache[slug] = {
                'slug': slug,
                'condition_id': item.get('conditionId'),
                'title': item.get('question'),
                'start_time': item.get('startDate'),
                'expiry_time': item.get('endDate'),
                'closed': item.get('closed'),
                'active': item.get('active'),
                'resolved_by': item.get('resolvedBy'),
                'uma_resolution_statuses': item.get('umaResolutionStatuses'),
                'outcomes': item.get('outcomes'),
                'outcome_prices': item.get('outcomePrices'),
                'resolution_source': item.get('resolutionSource'),
                'status': 'FOUND',
            }
            pending.remove(slug)
        offset += len(page)
        CACHE.write_text(json.dumps(cache, indent=2), encoding='utf-8')
        print(f'offset={offset} remaining={len(pending)}', flush=True)
        if len(page) < 100:
            break
    for slug in list(pending):
        match = re.fullmatch(r'(?:btc|eth)-updown-(5m|15m)-(\d+)', slug)
        if not match:
            continue
        duration = 300 if match.group(1) == '5m' else 900
        start = int(match.group(2))
        cache[slug] = {
            'slug': slug,
            'condition_id': None,
            'title': None,
            'start_time': datetime.datetime.fromtimestamp(start, datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
            'expiry_time': datetime.datetime.fromtimestamp(start + duration, datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
            'closed': None,
            'active': None,
            'resolved_by': None,
            'uma_resolution_statuses': None,
            'outcomes': ['UP', 'DOWN'],
            'outcome_prices': None,
            'resolution_source': None,
            'status': 'INFERRED_FROM_SLUG',
        }
        pending.remove(slug)
    CACHE.write_text(json.dumps(cache, indent=2), encoding='utf-8')
    print(json.dumps({'slugs': len(slugs), 'cached': len(cache), 'found': sum(item.get('status') == 'FOUND' for item in cache.values())}))


if __name__ == '__main__':
    main()
