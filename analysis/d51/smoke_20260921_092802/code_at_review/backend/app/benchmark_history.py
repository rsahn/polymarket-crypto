import asyncio
import os
import time
from pathlib import Path

from app.collectors.public_activity import BenchmarkWallet, PublicActivityCollector, normalize_activity
from app.storage.db import Database

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'phase_c_benchmarks.db'))
BATCH_SIZE = 1000


def bonereaper_wallet():
    address = os.getenv('POLYMARKET_BONEREAPER_ADDRESS')
    if not address:
        raise SystemExit('Set POLYMARKET_BONEREAPER_ADDRESS before starting Phase C.')
    return BenchmarkWallet('Bonereaper', address)


async def import_wallet(wallet, collector, db, window_days=1, test_start=None, test_end=None):
    oldest = collector._request({
        'user': wallet.address, 'type': 'TRADE', 'limit': 1, 'offset': 0,
        'start': 1, 'sortBy': 'TIMESTAMP', 'sortDirection': 'ASC',
    })
    if not oldest:
        print(f'{wallet.name}: no public trades found')
        return
    start = test_start or int(oldest[0].get('timestamp') or 1)
    end = test_end or int(time.time())
    checkpoint = await db.get_benchmark_checkpoint(wallet.name)
    inserted_total = checkpoint[3] if checkpoint else 0
    if checkpoint and checkpoint[4] == 'WINDOW_COMPLETE':
        start = max(start, checkpoint[2] + 1)
    elif checkpoint and checkpoint[4] == 'RUNNING':
        start = max(start, checkpoint[2])

    window_seconds = window_days * 86400
    downloaded = inserted_total
    duplicates = 0
    invalid = 0
    requests = 0
    began = time.time()
    current = start
    while current <= end:
        window_end = min(current + window_seconds - 1, end)
        batch = []
        await db.save_benchmark_checkpoint(wallet.name, current, window_end, current, inserted_total, 'RUNNING')
        for page in collector.iter_window_pages(wallet.address, current, window_end):
            requests += 1
            for raw in page:
                try:
                    row = normalize_activity(raw, wallet.name)
                    if not row['timestamp'] or row['side'] not in {'BUY', 'SELL'} or not row['outcome'] or row['price'] < 0 or row['size'] < 0 or not row['condition_id']:
                        invalid += 1
                        continue
                    batch.append(row)
                except (TypeError, ValueError, KeyError):
                    invalid += 1
                if len(batch) >= BATCH_SIZE:
                    last_cursor = max(row['timestamp'] for row in batch)
                    added = await db.insert_benchmark_activity(batch)
                    duplicates += len(batch) - added
                    inserted_total += added
                    downloaded += len(batch)
                    batch.clear()
                    elapsed = max(time.time() - began, 0.001)
                    total = await db.benchmark_total(wallet.name)
                    print(f'{wallet.name.upper()} downloaded={downloaded:,} inserted={inserted_total:,} duplicates={duplicates:,} invalid_records={invalid:,} requests={requests:,} current_window={current}:{window_end} elapsed_time={elapsed:.1f}s rows/sec={downloaded / elapsed:.1f} DB total={total:,}', flush=True)
                    await db.save_benchmark_checkpoint(wallet.name, current, window_end, last_cursor, inserted_total, 'RUNNING')
        if batch:
            added = await db.insert_benchmark_activity(batch)
            duplicates += len(batch) - added
            inserted_total += added
            downloaded += len(batch)
        await db.save_benchmark_checkpoint(wallet.name, current, window_end, window_end, inserted_total, 'WINDOW_COMPLETE')
        print(f'{wallet.name.upper()} window: {current} -> {window_end} downloaded={downloaded:,} inserted={inserted_total:,} duplicates={duplicates:,} invalid_records={invalid:,} requests={requests:,} checkpoint=SAVED', flush=True)
        current = window_end + 1

    await db.save_benchmark_checkpoint(wallet.name, end, end, end, inserted_total, 'COMPLETE')
    print(f'{wallet.name.upper()} COMPLETE inserted={inserted_total:,} duplicates={duplicates:,} invalid_records={invalid:,} requests={requests:,}', flush=True)


async def main():
    wallet = bonereaper_wallet()
    collector = PublicActivityCollector()
    validation = collector.validate_wallet(wallet)
    print(f'Bonereaper -> {wallet.address} | profile={validation["profile"].get("name")} | sample=10 validated', flush=True)
    db = Database(DB_PATH)
    await db.init()
    test_start = int(os.getenv('PHASE_C_TEST_START', '0')) or None
    test_end = int(os.getenv('PHASE_C_TEST_END', '0')) or None
    await import_wallet(wallet, collector, db, int(os.getenv('PHASE_C_WINDOW_DAYS', '1')), test_start, test_end)


if __name__ == '__main__':
    asyncio.run(main())
