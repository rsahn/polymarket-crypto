# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 30.406107300077565
- WALL_DURATION_SECONDS: 30.489
- TOTAL_EVENTS: 14435
- ROWS: 14289
- 5M_MARKETS: 1
- 15M_MARKETS: 1
- ROTATIONS_BY_DURATION: {"15m":0,"5m":0}
- RECONNECTIONS: {"binance":0,"polymarket":0}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 43
- OUT_OF_ORDER_REJECTED: 41
- SQLITE_INTEGRITY_CHECK: ["ok"]
- FOREIGN_KEY_VIOLATIONS: []
- OPEN_ANCHORS: 0
- REPLAY_HASHES_EQUAL: true
- NO_TRADE_VERIFIED: true
- QUALITY_REVIEW_PASSED: false
- QUALITY_FAILURES: ["5M_ROTATION_NOT_OBSERVED","DURATION_BELOW_24H","GAPS_REQUIRE_REVIEW_15m","GAPS_REQUIRE_REVIEW_5m","GAPS_REQUIRE_REVIEW_BTC","INSUFFICIENT_COVERAGE_15m","INSUFFICIENT_COVERAGE_5m","INSUFFICIENT_COVERAGE_BTC","RECONNECT_NOT_OBSERVED"]
- RESEARCH_ALLOWED: false

## Gaps, including rotations and session boundaries

```json
{
  "15m": {
    "events": 4854,
    "first_ms": 1789887825590,
    "last_ms": 1789887845153,
    "max_gap_ms": 520,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 19.563,
    "initial_gap_ms": 912,
    "trailing_gap_ms": 10014
  },
  "5m": {
    "events": 9435,
    "first_ms": 1789887825598,
    "last_ms": 1789887845114,
    "max_gap_ms": 479,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 19.516,
    "initial_gap_ms": 920,
    "trailing_gap_ms": 10053
  },
  "BTC": {
    "events": 96,
    "first_ms": 1789887826342,
    "last_ms": 1789887845155,
    "max_gap_ms": 1816,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 18.813,
    "initial_gap_ms": 1664,
    "trailing_gap_ms": 10012
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 14435,
    "decision_sha256": "6627f5cbb878197a339c3852f50b97688b7c463142a584794ecf57d020688ea5",
    "result_sha256": "743b99cbe884ac5c6794b3c00434e22314c5d5deb9200cfa1d364d500d3aaf85"
  },
  {
    "replay": 2,
    "event_count": 14435,
    "decision_sha256": "6627f5cbb878197a339c3852f50b97688b7c463142a584794ecf57d020688ea5",
    "result_sha256": "743b99cbe884ac5c6794b3c00434e22314c5d5deb9200cfa1d364d500d3aaf85"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
