"""Discover ALL active crypto Up/Down markets across timeframes.

Scans gamma-api for all active Up/Down markets (5m, 15m, 1h)
across supported cryptos: BTC, ETH, SOL, and any others available.
Returns a list of market specs for parallel trading.
"""
import hashlib, json, re, time, urllib.request

_GAMMA_BASE = "https://gamma-api.polymarket.com"

# Supported crypto symbols and their market slugs
CRYPTO_SYMBOLS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
}

# Timeframes in seconds
TIMEFRAMES = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}


def discover_all():
    """Discover ALL active crypto Up/Down markets.

    Returns
    -------
    list of dict, each with keys:
        crypto, timeframe_s, condition_id, token_up, token_down,
        market_slug, expiry_ts_ms, source_digest, discovered_ms
    """
    from app.collectors.polymarket import PolymarketMarketDiscovery
    from app.d5.identity import MarketIdentity

    now_s = int(time.time())
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    results = []
    errors = []

    for crypto, crypto_slug in CRYPTO_SYMBOLS.items():
        for tf_label, tf_seconds in TIMEFRAMES.items():
            slot_s = now_s // tf_seconds * tf_seconds
            slug = f"{crypto_slug}-updown-{tf_label}-{slot_s}"

            # Try current slot, then previous
            for attempt in range(2):
                try:
                    url = f"{_GAMMA_BASE}/markets?slug={slug}"
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as r:
                        values = json.loads(r.read(50000))

                    if not isinstance(values, list):
                        raise ValueError(f"RESPONSE_SHAPE: {type(values).__name__}")

                    if len(values) == 1:
                        raw = values[0]
                        parsed = PolymarketMarketDiscovery.parse_market_list(values)
                        if len(parsed) != 1:
                            raise ValueError("PARSE_FAILED")

                        market = MarketIdentity.from_market(parsed[0])

                        # Validate
                        if bool(raw.get("closed", True)):
                            raise ValueError("CLOSED")
                        if not bool(raw.get("active", False)):
                            raise ValueError("NOT_ACTIVE")
                        if not bool(raw.get("acceptingOrders", False)):
                            raise ValueError("NOT_ACCEPTING")

                        if not re.fullmatch(r"0x[0-9a-fA-F]{64}", market.condition_id):
                            raise ValueError(f"INVALID_CONDITION_ID")
                        if market.token_up == market.token_down:
                            raise ValueError("IDENTICAL_TOKENS")
                        if not market.token_up.isdigit() or not market.token_down.isdigit():
                            raise ValueError("NON_DIGIT_TOKENS")

                        source_digest = hashlib.sha256(
                            json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str).encode()
                        ).hexdigest()

                        results.append({
                            "crypto": crypto,
                            "crypto_slug": crypto_slug,
                            "timeframe_s": tf_seconds,
                            "timeframe_label": tf_label,
                            "condition_id": market.condition_id,
                            "token_up": market.token_up,
                            "token_down": market.token_down,
                            "market_slug": slug,
                            "expiry_ts_ms": market.expiry_ts_ms,
                            "source_digest": source_digest,
                            "discovered_ms": int(time.time() * 1000),
                        })
                        break  # found it, move on

                    # Try previous slot
                    slot_s -= tf_seconds
                    slug = f"{crypto_slug}-updown-{tf_label}-{slot_s}"

                except Exception as exc:
                    if attempt == 1:
                        errors.append(f"{crypto}/{tf_label}: {exc}")
                    continue

    if not results:
        raise ValueError(f"NO_MARKETS_FOUND: {errors}")

    return results, errors


def discover_by_timeframe(timeframe_s=300, max_markets=5):
    """Discover markets for a specific timeframe, limited to top N.

    Useful for starting small and scaling up gradually.
    """
    all_markets, errors = discover_all()
    filtered = [m for m in all_markets if m["timeframe_s"] == timeframe_s]
    return filtered[:max_markets], errors


def discover_btc_only():
    """Legacy: discover only BTC 5m (backward compat)."""
    from .market_discovery import discover_current
    return discover_current()
