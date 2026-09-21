# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 1321.822154100053
- WALL_DURATION_SECONDS: 1332.724
- TOTAL_EVENTS: 818688
- ROWS: 776312
- 5M_MARKETS: 5
- 15M_MARKETS: 2
- ROTATIONS_BY_DURATION: {"15m":1,"5m":4}
- RECONNECTIONS: {"binance":0,"polymarket":10}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 743
- OUT_OF_ORDER_REJECTED: 677
- SQLITE_INTEGRITY_CHECK: ["ok"]
- FOREIGN_KEY_VIOLATIONS: []
- OPEN_ANCHORS: 0
- REPLAY_HASHES_EQUAL: true
- NO_TRADE_VERIFIED: true
- QUALITY_REVIEW_PASSED: false
- QUALITY_FAILURES: ["ACCEPTED_AFTER_COLLECTION_STOP","RECEIVE_CLOCK_REGRESSION","RECONNECT_GAP_OVER_5S"]
- RESEARCH_ALLOWED: false

## Gaps, including rotations and session boundaries

```json
{
  "15m": {
    "events": 411217,
    "first_ms": 1789980374694,
    "last_ms": 1789981696536,
    "max_gap_ms": 1739,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1321.842,
    "initial_gap_ms": 824,
    "trailing_gap_ms": 0
  },
  "5m": {
    "events": 365095,
    "first_ms": 1789980374747,
    "last_ms": 1789981695718,
    "max_gap_ms": 7949,
    "gaps_over_5s": 4,
    "gap_time_ms": 27834,
    "receive_regressions": 0,
    "examples": [
      {
        "from_ms": 1789980599824,
        "to_ms": 1789980607773,
        "gap_ms": 7949
      },
      {
        "from_ms": 1789980884192,
        "to_ms": 1789980889326,
        "gap_ms": 5134
      },
      {
        "from_ms": 1789981499265,
        "to_ms": 1789981506394,
        "gap_ms": 7129
      },
      {
        "from_ms": 1789981636390,
        "to_ms": 1789981644012,
        "gap_ms": 7622
      }
    ],
    "coverage_seconds": 1320.971,
    "initial_gap_ms": 877,
    "trailing_gap_ms": 30
  },
  "BTC": {
    "events": 41548,
    "first_ms": 1789980375366,
    "last_ms": 1789981695747,
    "max_gap_ms": 3815,
    "gaps_over_5s": 0,
    "gap_time_ms": 0,
    "receive_regressions": 0,
    "examples": [],
    "coverage_seconds": 1320.381,
    "initial_gap_ms": 1496,
    "trailing_gap_ms": 1
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 818688,
    "decision_sha256": "0d4eff77e110a0bdf69aae33dc642aca0bab39e2cae646b07e493f5f2fe8cf74",
    "result_sha256": "8b4eb7aaee38b40ebb4e173a0cf1655cdd8779fea84f6d021a1eb787d9f001ba"
  },
  {
    "replay": 2,
    "event_count": 818688,
    "decision_sha256": "0d4eff77e110a0bdf69aae33dc642aca0bab39e2cae646b07e493f5f2fe8cf74",
    "result_sha256": "8b4eb7aaee38b40ebb4e173a0cf1655cdd8779fea84f6d021a1eb787d9f001ba"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
