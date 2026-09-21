# D5.1 instrumentation smoke

{
  "protocol": "D5.1",
  "historical_D5_DATA_QUALITY": "FAIL",
  "D51_DATA_QUALITY": "FAIL",
  "failures": [
    "ACCEPTED_AFTER_COLLECTION_STOP",
    "RECEIVE_CLOCK_REGRESSION",
    "RECONNECT_GAP_OVER_5S"
  ],
  "source_sha256": "bd81583fc431846c8ce1140c364dbfb1f62b884d6df90b3b2e4e081fc2f90d3f",
  "source_stat_unchanged": true,
  "smoke_only": true,
  "statistical_D6_validation": false,
  "research_allowed": false,
  "paper_started": false,
  "replays": [
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
  ],
  "gap_policy": "D5.1 QUALITY_PROTOCOL.md: verified transitions <=10s; internal/reconnect <=5s; endpoints <=10s"
}

Legacy-format FINAL_DATA_QUALITY_REPORT.md is an intermediate metrics rendering; its legacy gap-policy prose does not describe D5.1. This separate report and frozen protocol are authoritative for this new experiment only.
