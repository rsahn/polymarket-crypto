"""Find what happened to the XRP/SOL/ETH 4:50PM slots."""
import urllib.request, json

# The slug format uses timestamp - find current active slugs
base = "https://gamma-api.polymarket.com"
url = f"{base}/markets?tag=crypto&limit=100"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.loads(r.read(100000))

# Find our expired slugs
target_slugs = [
    "xrp-updown-5m-1791319800",
    "sol-updown-5m-1791319800",
    "eth-updown-5m-1791319800",
]

# Also find any resolution data
for m in data:
    slug = m.get("slug", "")
    if any(t in slug for t in ["xrp-updown-5m", "sol-updown-5m", "eth-updown-5m"]):
        prices = json.loads(m.get("outcomePrices", '["?","?"]'))
        end_date = m.get("endDate", "?")
        closed = m.get("closed", "?")
        print(f"{slug}")
        print(f"  End: {end_date}  Closed: {closed}")
        print(f"  UP={prices[0]} DOWN={prices[1]}")
        print(f"  Bid={m.get('bestBid')} Ask={m.get('bestAsk')}")
        print()
