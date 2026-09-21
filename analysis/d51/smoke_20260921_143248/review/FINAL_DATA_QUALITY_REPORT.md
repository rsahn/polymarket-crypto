# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 1320.0051229000092
- WALL_DURATION_SECONDS: 1328.321
- TOTAL_EVENTS: 1400618
- ROWS: 1371683
- 5M_MARKETS: 6
- 15M_MARKETS: 2
- ROTATIONS_BY_DURATION: {"15m":1,"5m":5}
- RECONNECTIONS: {"binance":0,"polymarket":6}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 1898
- OUT_OF_ORDER_REJECTED: 1246
- SQLITE_INTEGRITY_CHECK: ["ok"]
- FOREIGN_KEY_VIOLATIONS: []
- OPEN_ANCHORS: 0
- REPLAY_HASHES_EQUAL: true
- NO_TRADE_VERIFIED: true
- QUALITY_REVIEW_PASSED: true
- QUALITY_FAILURES: []
- RESEARCH_ALLOWED: false

## Gaps, including rotations and session boundaries

```json
{
  "5m": {
    "events": 932345,
    "first_ms": 1789994009696,
    "last_ms": 1789995328878,
    "max_gap_ms": 1207,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1319.182,
    "initial_gap_ms": 878,
    "trailing_gap_ms": 2
  },
  "15m": {
    "events": 439338,
    "first_ms": 1789994009782,
    "last_ms": 1789995328875,
    "max_gap_ms": 1503,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1319.093,
    "initial_gap_ms": 964,
    "trailing_gap_ms": 5
  },
  "BTC": {
    "events": 26956,
    "first_ms": 1789994010360,
    "last_ms": 1789995328672,
    "max_gap_ms": 2255,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1318.312,
    "initial_gap_ms": 1542,
    "trailing_gap_ms": 208
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 1400618,
    "decision_sha256": "1e1b559a6d586d717a4f3034b495c2574f6edc34fc27f0c44242f85b2f41677c",
    "result_sha256": "9c98f4bf1f8db560b3dd63545855db725639b4489aa558d520409e5e7297fa54"
  },
  {
    "replay": 2,
    "event_count": 1400618,
    "decision_sha256": "1e1b559a6d586d717a4f3034b495c2574f6edc34fc27f0c44242f85b2f41677c",
    "result_sha256": "9c98f4bf1f8db560b3dd63545855db725639b4489aa558d520409e5e7297fa54"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
