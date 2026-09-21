# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 1320.0072473000037
- WALL_DURATION_SECONDS: 1330.095
- TOTAL_EVENTS: 1366126
- ROWS: 1329698
- 5M_MARKETS: 6
- 15M_MARKETS: 2
- ROTATIONS_BY_DURATION: {"15m":1,"5m":5}
- RECONNECTIONS: {"binance":0,"polymarket":10}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 1963
- OUT_OF_ORDER_REJECTED: 1568
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
    "events": 412881,
    "first_ms": 1789984151549,
    "last_ms": 1789985470828,
    "max_gap_ms": 2818,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1319.279,
    "initial_gap_ms": 770,
    "trailing_gap_ms": 11
  },
  "5m": {
    "events": 916817,
    "first_ms": 1789984151581,
    "last_ms": 1789985470837,
    "max_gap_ms": 2940,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1319.256,
    "initial_gap_ms": 802,
    "trailing_gap_ms": 2
  },
  "BTC": {
    "events": 34376,
    "first_ms": 1789984152287,
    "last_ms": 1789985470801,
    "max_gap_ms": 2054,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1318.514,
    "initial_gap_ms": 1508,
    "trailing_gap_ms": 38
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 1366126,
    "decision_sha256": "422e893ebbcef9144a3c82ebb58ab8611918953285a9e4d6e44a1db34b903120",
    "result_sha256": "f029be0b486dfacc53c4c44a383b32a851b1043204916737445bf4b2928f9b9b"
  },
  {
    "replay": 2,
    "event_count": 1366126,
    "decision_sha256": "422e893ebbcef9144a3c82ebb58ab8611918953285a9e4d6e44a1db34b903120",
    "result_sha256": "f029be0b486dfacc53c4c44a383b32a851b1043204916737445bf4b2928f9b9b"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
