# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 1320.219239099999
- WALL_DURATION_SECONDS: 1328.916
- TOTAL_EVENTS: 760478
- ROWS: 745392
- 5M_MARKETS: 6
- 15M_MARKETS: 3
- ROTATIONS_BY_DURATION: {"15m":2,"5m":5}
- RECONNECTIONS: {"binance":0,"polymarket":6}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 1461
- OUT_OF_ORDER_REJECTED: 1007
- SQLITE_INTEGRITY_CHECK: ["ok"]
- FOREIGN_KEY_VIOLATIONS: []
- OPEN_ANCHORS: 0
- REPLAY_HASHES_EQUAL: true
- NO_TRADE_VERIFIED: true
- QUALITY_REVIEW_PASSED: false
- QUALITY_FAILURES: ["W32TIME_SYNC_ERROR"]
- RESEARCH_ALLOWED: false

## Gaps, including rotations and session boundaries

```json
{
  "5m": {
    "events": 444354,
    "first_ms": 1789975722453,
    "last_ms": 1789977041659,
    "max_gap_ms": 1618,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1319.206,
    "initial_gap_ms": 890,
    "trailing_gap_ms": 171
  },
  "15m": {
    "events": 301038,
    "first_ms": 1789975722591,
    "last_ms": 1789977041829,
    "max_gap_ms": 1514,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1319.238,
    "initial_gap_ms": 1028,
    "trailing_gap_ms": 1
  },
  "BTC": {
    "events": 13541,
    "first_ms": 1789975723428,
    "last_ms": 1789977041661,
    "max_gap_ms": 3438,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1318.233,
    "initial_gap_ms": 1865,
    "trailing_gap_ms": 169
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 760478,
    "decision_sha256": "046225ccc1d6f4d5e93e2f60d605069805406f01c1bdf267da6e034b69667b12",
    "result_sha256": "59812d88afeff2c65b169e366268476200e122a86dc2f18f629d628eef75ac3c"
  },
  {
    "replay": 2,
    "event_count": 760478,
    "decision_sha256": "046225ccc1d6f4d5e93e2f60d605069805406f01c1bdf267da6e034b69667b12",
    "result_sha256": "59812d88afeff2c65b169e366268476200e122a86dc2f18f629d628eef75ac3c"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
