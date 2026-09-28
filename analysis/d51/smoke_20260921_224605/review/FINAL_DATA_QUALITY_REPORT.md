# D5 SHADOW — DATA QUALITY REPORT

- ACTUAL_DURATION_SECONDS: 1320.0045521000866
- WALL_DURATION_SECONDS: 1326.959
- TOTAL_EVENTS: 639880
- ROWS: 624251
- 5M_MARKETS: 5
- 15M_MARKETS: 2
- ROTATIONS_BY_DURATION: {"15m":1,"5m":4}
- RECONNECTIONS: {"binance":21,"polymarket":382}
- CROSS_MARKET_VIOLATIONS: 0
- POST_EXPIRY_ACCEPTED: 0
- MISSING_TOKEN_IDS: 0
- REJECTED_EVENTS: 1237
- OUT_OF_ORDER_REJECTED: 836
- SQLITE_INTEGRITY_CHECK: ["ok"]
- FOREIGN_KEY_VIOLATIONS: []
- OPEN_ANCHORS: 0
- REPLAY_HASHES_EQUAL: true
- NO_TRADE_VERIFIED: true
- QUALITY_REVIEW_PASSED: false
- QUALITY_FAILURES: ["ACCEPTED_AFTER_COLLECTION_STOP","RECONNECT_GAP_OVER_5S"]
- RESEARCH_ALLOWED: false

## Gaps, including rotations and session boundaries

```json
{
  "15m": {
    "events": 216675,
    "first_ms": 1790023605754,
    "last_ms": 1790024925068,
    "max_gap_ms": 5444,
    "gaps_over_5s": 1,
    "gap_time_ms": 5444,
    "receive_regressions": 0,
    "examples": [
      {
        "from_ms": 1790023729559,
        "to_ms": 1790023735003,
        "gap_ms": 5444
      }
    ],
    "coverage_seconds": 1319.314,
    "initial_gap_ms": 775,
    "trailing_gap_ms": 0
  },
  "5m": {
    "events": 407576,
    "first_ms": 1790023605824,
    "last_ms": 1790024925065,
    "max_gap_ms": 5537,
    "gaps_over_5s": 1,
    "gap_time_ms": 5537,
    "receive_regressions": 0,
    "examples": [
      {
        "from_ms": 1790023871113,
        "to_ms": 1790023876650,
        "gap_ms": 5537
      }
    ],
    "coverage_seconds": 1319.241,
    "initial_gap_ms": 845,
    "trailing_gap_ms": 3
  },
  "BTC": {
    "events": 13520,
    "first_ms": 1790023606333,
    "last_ms": 1790024924678,
    "max_gap_ms": 13933,
    "gaps_over_5s": 20,
    "gap_time_ms": 251718,
    "receive_regressions": 0,
    "examples": [
      {
        "from_ms": 1790023623835,
        "to_ms": 1790023636194,
        "gap_ms": 12359
      },
      {
        "from_ms": 1790023665259,
        "to_ms": 1790023679192,
        "gap_ms": 13933
      },
      {
        "from_ms": 1790023682275,
        "to_ms": 1790023694791,
        "gap_ms": 12516
      },
      {
        "from_ms": 1790023704818,
        "to_ms": 1790023717188,
        "gap_ms": 12370
      },
      {
        "from_ms": 1790023788599,
        "to_ms": 1790023800875,
        "gap_ms": 12276
      },
      {
        "from_ms": 1790023801115,
        "to_ms": 1790023813969,
        "gap_ms": 12854
      },
      {
        "from_ms": 1790023882365,
        "to_ms": 1790023894807,
        "gap_ms": 12442
      },
      {
        "from_ms": 1790023924629,
        "to_ms": 1790023936633,
        "gap_ms": 12004
      },
      {
        "from_ms": 1790023986013,
        "to_ms": 1790023998576,
        "gap_ms": 12563
      },
      {
        "from_ms": 1790024003434,
        "to_ms": 1790024016378,
        "gap_ms": 12944
      },
      {
        "from_ms": 1790024023868,
        "to_ms": 1790024036125,
        "gap_ms": 12257
      },
      {
        "from_ms": 1790024050821,
        "to_ms": 1790024064114,
        "gap_ms": 13293
      },
      {
        "from_ms": 1790024070211,
        "to_ms": 1790024082561,
        "gap_ms": 12350
      },
      {
        "from_ms": 1790024151139,
        "to_ms": 1790024163722,
        "gap_ms": 12583
      },
      {
        "from_ms": 1790024289993,
        "to_ms": 1790024302255,
        "gap_ms": 12262
      },
      {
        "from_ms": 1790024344711,
        "to_ms": 1790024357152,
        "gap_ms": 12441
      },
      {
        "from_ms": 1790024408916,
        "to_ms": 1790024421214,
        "gap_ms": 12298
      },
      {
        "from_ms": 1790024586425,
        "to_ms": 1790024598919,
        "gap_ms": 12494
      },
      {
        "from_ms": 1790024702849,
        "to_ms": 1790024715699,
        "gap_ms": 12850
      },
      {
        "from_ms": 1790024764596,
        "to_ms": 1790024777225,
        "gap_ms": 12629
      }
    ],
    "coverage_seconds": 1318.345,
    "initial_gap_ms": 1354,
    "trailing_gap_ms": 390
  }
}
```

## Replays

```json
[
  {
    "replay": 1,
    "event_count": 639880,
    "decision_sha256": "8cb3ffab40bd1c92ef0657dc2800180b8d6e5ffb2ded916d19ea8d8b40c1c338",
    "result_sha256": "4029f6624f2321034a86405ca5a0c7e02595d1e1096f367500054842ef1aafba"
  },
  {
    "replay": 2,
    "event_count": 639880,
    "decision_sha256": "8cb3ffab40bd1c92ef0657dc2800180b8d6e5ffb2ded916d19ea8d8b40c1c338",
    "result_sha256": "4029f6624f2321034a86405ca5a0c7e02595d1e1096f367500054842ef1aafba"
  }
]
```

No D5 Research was started. Source and reception timestamps were not corrected or backfilled.
