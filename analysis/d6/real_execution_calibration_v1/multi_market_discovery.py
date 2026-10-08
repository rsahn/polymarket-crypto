"""Discover ALL active crypto Up/Down markets across timeframes.

CORRECT SLUGS: btc, eth, sol, xrp, doge (ticker, not full name).
Scans gamma-api for all active Up/Down markets (5m, 15m, 1h).
Self-contained: no dependency on app/ modules.
"""
import hashlib, json, re, time, urllib.request

_GAMMA_BASE = "https://gamma-api.polymarket.com"

# REAL slug prefixes (from browser inspection)
CRYPTO_SLUGS = {
    "BTC": "btc",
    "ETH": "eth",
    "SOL": "sol",
    "XRP": "xrp",
    "DOGE": "doge",
}

# Binance ticker symbols for price feeds
BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
    "DOGE": "DOGEUSDT",
}

TIMEFRAMES = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}


def discover_crypto(crypto, tf_label="5m"):
    """Discover a single crypto's active Up/Down market for the current slot.

    Returns one market dict or raises ValueError.
    """
    if crypto not in CRYPTO_SLUGS:
        raise ValueError(f"UNKNOWN_CRYPTO: {crypto}")
    prefix = CRYPTO_SLUGS[crypto]
    tf_seconds = TIMEFRAMES.get(tf_label, 300)
    now_s = int(time.time())
    slot_s = now_s // tf_seconds * tf_seconds

    for attempt in range(2):
        try:
            slug = f"{prefix}-updown-{tf_label}-{slot_s}"
            url = f"{_GAMMA_BASE}/markets?slug={slug}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as r:
                values = json.loads(r.read(50000))

            if not isinstance(values, list) or len(values) == 0:
                slot_s -= tf_seconds
                continue

            if len(values) != 1:
                raise ValueError(f"AMBIGUOUS: {len(values)}")

            raw = values[0]

            if bool(raw.get("closed", True)):
                raise ValueError("CLOSED")
            if not bool(raw.get("active", False)):
                raise ValueError("NOT_ACTIVE")
            if not bool(raw.get("acceptingOrders", False)):
                raise ValueError("NOT_ACCEPTING")

            condition_id = raw.get("conditionId", "")
            import re
            if not re.fullmatch(r"0x[0-9a-fA-F]{64}", condition_id):
                raise ValueError(f"INVALID_CONDITION_ID")

            clob_raw = raw.get("clobTokenIds", "[]")
            if isinstance(clob_raw, str):
                try:
                    ids = json.loads(clob_raw)
                except (json.JSONDecodeError, TypeError):
                    ids = []
            elif isinstance(clob_raw, list):
                ids = clob_raw
            else:
                ids = []
            ids = [str(x) for x in ids if x]

            if len(ids) < 2:
                raise ValueError("MISSING_TOKENS")
            token_up, token_down = ids[0], ids[1]

            if not token_up.isdigit() or not token_down.isdigit():
                raise ValueError(f"NON_DIGIT_TOKENS")
            if token_up == token_down:
                raise ValueError("IDENTICAL_TOKENS")

            import datetime
            end_date = raw.get("endDate", "")
            expiry_ts_ms = 0
            if end_date:
                try:
                    dt = datetime.datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    expiry_ts_ms = int(dt.timestamp() * 1000)
                except (ValueError, AttributeError):
                    expiry_ts_ms = int(time.time() * 1000) + 86400000

            return {
                "crypto": crypto,
                "prefix": prefix,
                "timeframe_s": tf_seconds,
                "timeframe_label": tf_label,
                "condition_id": condition_id,
                "token_up": token_up,
                "token_down": token_down,
                "market_slug": slug,
                "expiry_ts_ms": expiry_ts_ms,
                "slot_start_ts": slot_s * 1000,  # ms
            }

        except Exception as exc:
            if attempt == 1:
                raise ValueError(f"{crypto}/{tf_label}: {exc}") from exc
            continue

    raise ValueError(f"{crypto}/{tf_label}: NOT_FOUND")


def discover_all():
    """Discover ALL active crypto Up/Down markets.

    Returns
    -------
    (list_of_markets, list_of_errors)
    """
    now_s = int(time.time())
    results = []
    errors = []

    for crypto, prefix in CRYPTO_SLUGS.items():
        for tf_label, tf_seconds in TIMEFRAMES.items():
            slot_s = now_s // tf_seconds * tf_seconds

            for attempt in range(2):  # current slot, then previous
                try:
                    slug = f"{prefix}-updown-{tf_label}-{slot_s}"
                    url = f"{_GAMMA_BASE}/markets?slug={slug}"
                    req = urllib.request.Request(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "application/json",
                    })
                    with urllib.request.urlopen(req, timeout=10) as r:
                        values = json.loads(r.read(50000))

                    if not isinstance(values, list) or len(values) == 0:
                        slot_s -= tf_seconds
                        continue

                    if len(values) != 1:
                        raise ValueError(f"AMBIGUOUS: {len(values)}")

                    raw = values[0]

                    # Validate
                    if bool(raw.get("closed", True)):
                        raise ValueError("CLOSED")
                    if not bool(raw.get("active", False)):
                        raise ValueError("NOT_ACTIVE")
                    if not bool(raw.get("acceptingOrders", False)):
                        raise ValueError("NOT_ACCEPTING")

                    # conditionId (camelCase in gamma-api)
                    condition_id = raw.get("conditionId", "")
                    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", condition_id):
                        raise ValueError(f"INVALID_CONDITION_ID")

                    # Parse tokens from clobTokenIds JSON string
                    clob_raw = raw.get("clobTokenIds", "[]")
                    if isinstance(clob_raw, str):
                        try:
                            ids = json.loads(clob_raw)
                        except (json.JSONDecodeError, TypeError):
                            ids = []
                    elif isinstance(clob_raw, list):
                        ids = clob_raw
                    else:
                        ids = []
                    ids = [str(x) for x in ids if x]

                    if len(ids) < 2:
                        raise ValueError("MISSING_TOKENS")
                    token_up, token_down = ids[0], ids[1]

                    if not token_up.isdigit() or not token_down.isdigit():
                        raise ValueError(f"NON_DIGIT_TOKENS")
                    if token_up == token_down:
                        raise ValueError("IDENTICAL_TOKENS")

                    # Expiry
                    end_date = raw.get("endDate", "")
                    expiry_ts_ms = 0
                    if end_date:
                        try:
                            import datetime
                            dt = datetime.datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                            expiry_ts_ms = int(dt.timestamp() * 1000)
                        except (ValueError, AttributeError):
                            expiry_ts_ms = int(time.time() * 1000) + 86400000

                    source_digest = hashlib.sha256(
                        json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str).encode()
                    ).hexdigest()

                    results.append({
                        "crypto": crypto,
                        "prefix": prefix,
                        "timeframe_s": tf_seconds,
                        "timeframe_label": tf_label,
                        "condition_id": condition_id,
                        "token_up": token_up,
                        "token_down": token_down,
                        "market_slug": slug,
                        "expiry_ts_ms": expiry_ts_ms,
                        "source_digest": source_digest,
                        "discovered_ms": int(time.time() * 1000),
                    })
                    break  # found it

                except Exception as exc:
                    if attempt == 1:
                        errors.append(f"{crypto}/{tf_label}: {exc}")
                    continue

    if not results:
        raise ValueError(f"NO_MARKETS_FOUND: {errors}")

    return results, errors
