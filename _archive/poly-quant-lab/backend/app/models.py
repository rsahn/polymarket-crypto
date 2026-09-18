from dataclasses import dataclass
from typing import Optional

@dataclass(slots=True)
class MarketTick:
    source: str
    symbol: str
    event_ts_ms: Optional[int]
    recv_ts_ms: int
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_qty: Optional[float] = None
    ask_qty: Optional[float] = None

@dataclass(slots=True)
class PolyQuote:
    market_id: str
    token_id: str
    outcome: str
    recv_ts_ms: int
    bid: float
    ask: float
    bid_qty: float = 0.0
    ask_qty: float = 0.0
    event_ts_ms: Optional[int] = None

@dataclass(slots=True)
class Signal:
    strategy: str
    market_id: str
    ts_ms: int
    side: str
    score: float
    expected_edge: float
    metadata: dict
