# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 10944.725369399996
- WALL_DURATION_SECONDS: 10954.855
- TOTAL_EVENTS: 7518713
- ROWS: 7441212
- 5M_MARKETS: 38
- 15M_MARKETS: 13
- ROTATIONS_BY_DURATION: {"15m":12,"5m":37}
- RECONNECTIONS: {"binance":0,"polymarket":68}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 10335
- OUT_OF_ORDER_REJECTED: 7422
- SQLITE_INTEGRITY_CHECK: ["ok"]
- FOREIGN_KEY_VIOLATIONS: []
- OPEN_ANCHORS: 0
- REPLAY_HASHES_EQUAL: true
- NO_TRADE_VERIFIED: true
- QUALITY_REVIEW_PASSED: false
- QUALITY_FAILURES: ["GAPS_REQUIRE_REVIEW_15m","GAPS_REQUIRE_REVIEW_5m","GAPS_REQUIRE_REVIEW_BTC","UNCLEAN_STOP"]
- RESEARCH_ALLOWED: false

## Gaps, including rotations and session boundaries

```json
{
  "15m": {
    "events": 2842026,
    "first_ms": 1789901308186,
    "last_ms": 1789912251847,
    "max_gap_ms": 6551,
    "gaps_over_5s": 3,
    "gap_time_ms": 17677,
    "receive_regressions": 0,
    "examples": [
      {
        "from_ms": 1789903656383,
        "to_ms": 1789903662934,
        "gap_ms": 6551
      },
      {
        "from_ms": 1789906963945,
        "to_ms": 1789906969996,
        "gap_ms": 6051
      },
      {
        "from_ms": 1789909685294,
        "to_ms": 1789909690369,
        "gap_ms": 5075
      }
    ],
    "coverage_seconds": 10943.661,
    "initial_gap_ms": 919,
    "trailing_gap_ms": 256
  },
  "5m": {
    "events": 4599186,
    "first_ms": 1789901308218,
    "last_ms": 1789912251846,
    "max_gap_ms": 8557,
    "gaps_over_5s": 10,
    "gap_time_ms": 63475,
    "receive_regressions": 0,
    "examples": [
      {
        "from_ms": 1789902476409,
        "to_ms": 1789902481421,
        "gap_ms": 5012
      },
      {
        "from_ms": 1789902746655,
        "to_ms": 1789902751844,
        "gap_ms": 5189
      },
      {
        "from_ms": 1789903153937,
        "to_ms": 1789903158979,
        "gap_ms": 5042
      },
      {
        "from_ms": 1789903199814,
        "to_ms": 1789903205623,
        "gap_ms": 5809
      },
      {
        "from_ms": 1789903449348,
        "to_ms": 1789903455230,
        "gap_ms": 5882
      },
      {
        "from_ms": 1789903499971,
        "to_ms": 1789903505547,
        "gap_ms": 5576
      },
      {
        "from_ms": 1789904099995,
        "to_ms": 1789904108459,
        "gap_ms": 8464
      },
      {
        "from_ms": 1789905899532,
        "to_ms": 1789905908089,
        "gap_ms": 8557
      },
      {
        "from_ms": 1789906199758,
        "to_ms": 1789906207454,
        "gap_ms": 7696
      },
      {
        "from_ms": 1789910699775,
        "to_ms": 1789910706023,
        "gap_ms": 6248
      }
    ],
    "coverage_seconds": 10943.628,
    "initial_gap_ms": 951,
    "trailing_gap_ms": 257
  },
  "BTC": {
    "events": 66517,
    "first_ms": 1789901309170,
    "last_ms": 1789912251750,
    "max_gap_ms": 5457,
    "gaps_over_5s": 2,
    "gap_time_ms": 10837,
    "receive_regressions": 0,
    "examples": [
      {
        "from_ms": 1789901381514,
        "to_ms": 1789901386971,
        "gap_ms": 5457
      },
      {
        "from_ms": 1789901996738,
        "to_ms": 1789902002118,
        "gap_ms": 5380
      }
    ],
    "coverage_seconds": 10942.58,
    "initial_gap_ms": 1903,
    "trailing_gap_ms": 353
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 7518713,
    "decision_sha256": "6184bfe7562e14867bd18789f315bedd7d15d613662c1a948a13ef828d1cdaa7",
    "result_sha256": "00d76b967afeae5406afd09dabe1265550e6218f0bf67e13732a53c932ee9752"
  },
  {
    "replay": 2,
    "event_count": 7518713,
    "decision_sha256": "6184bfe7562e14867bd18789f315bedd7d15d613662c1a948a13ef828d1cdaa7",
    "result_sha256": "00d76b967afeae5406afd09dabe1265550e6218f0bf67e13732a53c932ee9752"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
