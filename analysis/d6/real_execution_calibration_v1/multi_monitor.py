"""Multi-crypto monitor — runs alongside run0165, read-only.

NO AsyncSecureClient, NO signatures, NO trades.
Just watches all crypto Up/Down markets and reports opportunities.
Safe to run in parallel with live-v1-run0165.
"""
import sys, json, time, urllib.request, os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from analysis.d6.real_execution_calibration_v1.multi_market_discovery import discover_all, BINANCE_SYMBOLS

_GAMMA = "https://gamma-api.polymarket.com"
MONITOR_DIR = Path("D:/polymarket-real-calibration/monitor")
MONITOR_DIR.mkdir(parents=True, exist_ok=True)

def fetch_json(url, max_kb=200):
    """Fetch and parse JSON with chunked response support."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        chunks = []
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if sum(len(c) for c in chunks) > max_kb * 1024:
                break
        return json.loads(b''.join(chunks))

def get_book_stats(market_slug):
    """Get current bid/ask spread for a market by slug."""
    url = f"{_GAMMA}/markets?slug={market_slug}"
    try:
        data = fetch_json(url, 50)
        if isinstance(data, list) and len(data) > 0:
            d = data[0]
            return {
                'best_bid': d.get('bestBid', '?'),
                'best_ask': d.get('bestAsk', '?'),
                'spread': d.get('spread', '?'),
                'last_trade': d.get('lastTradePrice', '?'),
                'volume': d.get('liquidity', '?'),
            }
    except Exception as e:
        return {'error': str(e)}
    return None

def main():
    print("=" * 60)
    print("  MULTI-CRYPTO MONITOR  (read-only, 0 conflict)")
    print("  Running alongside: live-v1-run0165")
    print("=" * 60)
    print()
    
    log_path = MONITOR_DIR / f"monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = open(log_path, 'w', encoding='utf-8')
    
    cycle = 0
    while True:
        cycle += 1
        now = datetime.now().strftime('%H:%M:%S')
        
        try:
            markets, errors = discover_all()
        except Exception as e:
            line = f"[{now}] Discovery error: {e}"
            print(line)
            log_file.write(line + '\n')
            log_file.flush()
            time.sleep(30)
            continue
        
        print(f"\n[{now}] === Cycle {cycle} — {len(markets)} markets ===", flush=True)
        log_file.write(f"[{now}] Cycle {cycle}: {len(markets)} markets\n")
        
        for m in markets:
            stats = get_book_stats(m['market_slug'])
            if stats and 'error' not in stats:
                bid = stats.get('best_bid', '?')
                ask = stats.get('best_ask', '?')
                last = stats.get('last_trade', '?')
                vol = stats.get('volume', '?')
                
                # Signal: if spread > threshold, potential opportunity
                spread_val = stats.get('spread')
                spread_pct = f"{float(spread_val)*100:.1f}%" if spread_val and spread_val != '?' else '?'
                
                print(f"  {m['crypto']:4s} {m['timeframe_label']:3s} | "
                      f"bid={bid} ask={ask} spread={spread_pct} "
                      f"last={last} vol={vol}", flush=True)
                
                log_file.write(f"{m['crypto']} {m['timeframe_label']} "
                             f"bid={bid} ask={ask} spread={spread_pct} "
                             f"last={last} vol={vol}\n")
            else:
                err = stats.get('error', 'unknown') if stats else 'no data'
                print(f"  {m['crypto']:4s} {m['timeframe_label']:3s} | error: {err}", flush=True)
        
        log_file.flush()
        time.sleep(60)  # check every 60s

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor stopped")
