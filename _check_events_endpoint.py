"""Check resolved markets - use events endpoint."""
import urllib.request, json

base = "https://gamma-api.polymarket.com"

# Check events for these specific slugs
event_slugs = [
    "xrp-updown-5m-1791319800",
    "sol-updown-5m-1791319800",
    "eth-updown-5m-1791319800",
]

for slug in event_slugs:
    # Try events endpoint
    url = f"{base}/events?slug={slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read(50000))
        if data:
            e = data[0]
            print(f"=== {slug} ===")
            print(f"  Active: {e.get('active')}")
            print(f"  Closed: {e.get('closed')}")
            print(f"  End date: {e.get('endDate')}")
            # Check if resolved
            markets = e.get("markets", [])
            if markets:
                for m in markets:
                    prices = json.loads(m.get("outcomePrices", '["?","?"]'))
                    print(f"  Market {m.get('id')}: UP={prices[0]} DOWN={prices[1]}")
            else:
                print(f"  No markets in event")
        else:
            print(f"{slug}: no event data")
    except Exception as ex:
        print(f"{slug}: ERROR {ex}")
    print()
