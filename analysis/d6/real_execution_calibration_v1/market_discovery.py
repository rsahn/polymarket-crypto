"""Discover the current active BTC Up/Down 5m market via gamma-api.
No credentials, no SDK, no mutations.
"""
import hashlib, json, re, time, urllib.request

_GAMMA_BASE = "https://gamma-api.polymarket.com"

def discover_current():
    """Discover the current active BTC Up/Down 5m market.

    Queries gamma-api with the current 5-minute slot slug, validates
    the market is active, not closed, and accepting orders.

    Returns
    -------
    dict with keys:
        condition_id, token_up, token_down, market_slug,
        expiry_ts_ms, source_digest, discovered_ms

    Raises
    ------
    ValueError on any validation failure.
    """
    # Late imports to avoid circular deps at module level
    from app.collectors.polymarket import PolymarketMarketDiscovery
    from app.d5.identity import MarketIdentity

    now_s = int(time.time())
    slot_s = now_s // 300 * 300
    slug = f"btc-updown-5m-{slot_s}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    url = f"{_GAMMA_BASE}/markets?slug={slug}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            values = json.loads(r.read(50000))
    except Exception as exc:
        raise ValueError(f"GAMMA_UNAVAILABLE: {exc}") from None

    if not isinstance(values, list):
        raise ValueError(f"MARKET_RESPONSE_SHAPE: expected list, got {type(values).__name__}")

    # If current slot has no market yet, try the previous slot
    if len(values) == 0:
        slot_s -= 300
        slug = f"btc-updown-5m-{slot_s}"
        url = f"{_GAMMA_BASE}/markets?slug={slug}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            values = json.loads(r.read(50000))
        if not isinstance(values, list) or len(values) == 0:
            raise ValueError(f"MARKET_NOT_FOUND: no active 5m slot")

    if len(values) != 1:
        raise ValueError(f"MARKET_AMBIGUOUS: {len(values)} results for {slug}")

    raw = values[0]
    parsed = PolymarketMarketDiscovery.parse_market_list(values)
    if len(parsed) != 1:
        raise ValueError(f"MARKET_PARSE_FAILED")

    market = MarketIdentity.from_market(parsed[0])

    # Verify slug match
    found_slug = str(raw.get("slug", ""))
    if found_slug != slug:
        raise ValueError(f"MARKET_SLUG_MISMATCH: expected {slug}, got {found_slug}")

    # Verify market is live
    closed = bool(raw.get("closed", True))
    active = bool(raw.get("active", False))
    accepting = bool(raw.get("acceptingOrders", False))
    if closed:
        raise ValueError(f"MARKET_CLOSED: {slug}")
    if not active:
        raise ValueError(f"MARKET_NOT_ACTIVE: {slug}")
    if not accepting:
        raise ValueError(f"MARKET_NOT_ACCEPTING_ORDERS: {slug}")

    # Verify condition_id
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", market.condition_id):
        raise ValueError(f"INVALID_CONDITION_ID: {market.condition_id}")

    # Verify tokens
    if market.token_up == market.token_down:
        raise ValueError(f"IDENTICAL_TOKENS")
    if not market.token_up.isdigit() or not market.token_down.isdigit():
        raise ValueError(f"NON_DIGIT_TOKENS")

    source_digest = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()

    return {
        "condition_id": market.condition_id,
        "token_up": market.token_up,
        "token_down": market.token_down,
        "market_slug": market.market_slug,
        "expiry_ts_ms": market.expiry_ts_ms,
        "source_digest": source_digest,
        "discovered_ms": int(time.time() * 1000),
    }
