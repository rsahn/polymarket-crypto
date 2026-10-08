"""Diagnose Polymarket Up/Down market discovery."""
import urllib.request, json, time

now_s = int(time.time())
tf = 300
slot_s = now_s // tf * tf

print(f"Current time: {now_s}")
print(f"Current 5m slot: {slot_s}")

# Try several slots around current time
for offset in [0, -300, -600, -900, -1200, -1500, 3600, 7200, 14400]:
    ts = slot_s + offset
    slug = f"btc-updown-5m-{ts}"
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read(50000))
        if data and len(data) > 0:
            m = data[0]
            print(f"\nFOUND: {slug}")
            print(f"  Condition ID: {m.get('conditionId')}")
            print(f"  Tokens: {m.get('clobTokenIds')}")
            print(f"  Active: {m.get('active')}, AcceptingOrders: {m.get('acceptingOrders')}, Closed: {m.get('closed')}")
        else:
            print(f"  {slug}: no market")
    except Exception as e:
        print(f"  {slug}: error - {e}")

# Also test: does the REST API accept the token IDs we have?
print("\n\n--- Testing book REST API with discovered tokens ---")
# BTC_5m token from the logs that said "no orderbook exists"
# Let's find it from the actual discovery
for crypto in ["BTC", "ETH", "SOL", "XRP", "DOGE"]:
    for offset in [0, -300, -600]:
        ts = slot_s + offset
        slug = f"{crypto.lower()}-updown-5m-{ts}"
        url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read(50000))
            if data and len(data) > 0:
                m = data[0]
                clob_raw = m.get("clobTokenIds", "[]")
                if isinstance(clob_raw, str):
                    ids = json.loads(clob_raw)
                else:
                    ids = clob_raw
                ids = [str(x) for x in ids if x]
                if ids:
                    print(f"\n{crypto} 5m-{ts}: tokens = {ids}")
                    # Test the REST book API directly
                    for tid in ids:
                        book_url = f"https://clob.polymarket.com/orderbook?token_id={tid}"
                        b_req = urllib.request.Request(book_url, headers={"User-Agent": "Mozilla/5.0"})
                        try:
                            with urllib.request.urlopen(b_req, timeout=10) as br:
                                bdata = json.loads(br.read(50000))
                            bids = bdata.get("bids", [])
                            asks = bdata.get("asks", [])
                            print(f"    Token {tid}: {len(bids)} bids, {len(asks)} asks")
                        except Exception as be:
                            print(f"    Token {tid}: book error - {be}")
                break
        except Exception as e:
            pass
