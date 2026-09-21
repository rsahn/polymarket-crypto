from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass


def assert_shadow(config=None):
    config = os.environ if config is None else config
    for key in ('LIVE_TRADING', 'ENABLE_LIVE_TRADING', 'REAL_TRADING', 'SEND_REAL_ORDERS'):
        if str(config.get(key, '')).strip().lower() not in ('', '0', 'false', 'no', 'off'):
            raise RuntimeError(f'D5 SHADOW ONLY: {key} is forbidden')
    for key in ('MODE', 'TRADING_MODE', 'D5_MODE'):
        if str(config.get(key, 'SHADOW')).strip().upper() not in ('SHADOW', 'PAPER'):
            raise RuntimeError(f'D5 SHADOW ONLY: {key} must be SHADOW/PAPER')
    for key in ('PAPER_SHADOW', 'D5_SHADOW'):
        if key in config and str(config[key]).strip().lower() not in ('1','true','yes','on'):
            raise RuntimeError(f'D5 SHADOW ONLY: {key} cannot be disabled')


@dataclass(frozen=True)
class MarketIdentity:
    market_duration: str
    market_slug: str
    condition_id: str
    token_up: str
    token_down: str
    expiry_ts_ms: int

    def __post_init__(self):
        if self.market_duration not in ('5m', '15m') or not all(
            (self.market_slug, self.condition_id, self.token_up, self.token_down)):
            raise ValueError('MISSING_MARKET_IDENTITY')
        if self.market_slug in ('5m','15m') or self.condition_id in ('5m','15m', self.market_slug):
            raise ValueError('PLACEHOLDER_MARKET_IDENTITY')
        if self.token_up == self.token_down or self.expiry_ts_ms <= 0:
            raise ValueError('INVALID_MARKET_IDENTITY')

    @property
    def key(self):
        return self.condition_id, self.market_slug

    def token(self, side):
        if side not in ('UP','DOWN'):
            raise ValueError(side)
        return self.token_up if side == 'UP' else self.token_down

    def fields(self):
        return asdict(self)

    @classmethod
    def from_market(cls, market):
        metadata = market.get('metadata') or {}
        tokens = market['token_ids']
        identity = cls(market['market_key'], market['slug'], metadata.get('conditionId') or '',
                       tokens['UP'], tokens['DOWN'], int(market['expiry_ts_ms']))
        # Live identity is accepted only from discovery metadata, never invented from time.
        if not re.fullmatch(r'btc-updown-(5m|15m)-\d+', identity.market_slug):
            raise ValueError('NON_BTC_UPDOWN_MARKET')
        if not re.fullmatch(r'0x[0-9a-fA-F]{64}', identity.condition_id):
            raise ValueError('INVALID_CONDITION_ID')
        labels = metadata.get('outcomes')
        import json
        if isinstance(labels, str):
            labels = json.loads(labels)
        if {str(x).upper() for x in (labels or [])} != {'UP','DOWN'}:
            raise ValueError('UNVERIFIED_OUTCOME_MAPPING')
        return identity

    def matches(self, snapshot):
        return all(snapshot.get(k) == v for k, v in self.fields().items()) and all(
            (snapshot.get(s.lower()) or {}).get('token_id') == self.token(s) for s in ('UP','DOWN'))
