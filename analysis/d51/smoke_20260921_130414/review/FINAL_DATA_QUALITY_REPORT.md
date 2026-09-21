# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 1320.013272000011
- WALL_DURATION_SECONDS: 1330.187
- TOTAL_EVENTS: 1279540
- ROWS: 1257795
- 5M_MARKETS: 6
- 15M_MARKETS: 2
- ROTATIONS_BY_DURATION: {"15m":1,"5m":5}
- RECONNECTIONS: {"binance":0,"polymarket":8}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 1806
- OUT_OF_ORDER_REJECTED: 1292
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
  "15m": {
    "events": 415908,
    "first_ms": 1789988695270,
    "last_ms": 1789990014329,
    "max_gap_ms": 984,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1319.059,
    "initial_gap_ms": 1070,
    "trailing_gap_ms": 8
  },
  "5m": {
    "events": 841887,
    "first_ms": 1789988695321,
    "last_ms": 1789990014318,
    "max_gap_ms": 2894,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1318.997,
    "initial_gap_ms": 1121,
    "trailing_gap_ms": 19
  },
  "BTC": {
    "events": 19854,
    "first_ms": 1789988696251,
    "last_ms": 1789990014093,
    "max_gap_ms": 1825,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1317.842,
    "initial_gap_ms": 2051,
    "trailing_gap_ms": 244
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 1279540,
    "decision_sha256": "35c20a26dd7b3b334b59a4f9bb19a529883cda9fa96700f686f1ba502bcf56bc",
    "result_sha256": "43d0d2d82a739daf81ee7590f9356912af9d51e6ad8e7e1029ba0a05be274845"
  },
  {
    "replay": 2,
    "event_count": 1279540,
    "decision_sha256": "35c20a26dd7b3b334b59a4f9bb19a529883cda9fa96700f686f1ba502bcf56bc",
    "result_sha256": "43d0d2d82a739daf81ee7590f9356912af9d51e6ad8e7e1029ba0a05be274845"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
