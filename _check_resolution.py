"""Check resolved markets via gamma."""
import urllib.request, json

slugs = [
    "xrp-updown-5m-1791319800",
    "sol-updown-5m-1791319800",
    "eth-updown-5m-1791319800",
]

for slug in slugs:
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read(50000))
    if data:
        m = data[0]
        prices = json.loads(m.get("outcomePrices", '["?","?"]'))
        print(f"--- {slug} ---")
        print(f"  Closed: {m.get('closed')}")
        print(f"  Active: {m.get('active')}")
        print(f"  Accepting orders: {m.get('acceptingOrders')}")
        print(f"  Outcome prices: UP={prices[0]}, DOWN={prices[1]}")
        print(f"  Best bid: {m.get('bestBid')}, Best ask: {m.get('bestAsk')}")
        print(f"  End date: {m.get('endDate')}")
        # Check events for resolution
        events = m.get("events", [])
        if events:
            print(f"  Event active: {events[0].get('active')}, closed: {events[0].get('closed')}")
    else:
        print(f"{slug}: no data")
    print()
