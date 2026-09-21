# D5.1 instrumentation smoke

{
  "protocol": "D5.1",
  "historical_D5_DATA_QUALITY": "FAIL",
  "D51_DATA_QUALITY": "FAIL",
  "failures": [
    "W32TIME_SYNC_ERROR"
  ],
  "source_sha256": "596f2a14f3ce2bde7623943d6f2046d101dd758de0af4309a176d4cac74a15fb",
  "source_stat_unchanged": true,
  "smoke_only": true,
  "statistical_D6_validation": false,
  "research_allowed": false,
  "paper_started": false,
  "replays": [
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
  ],
  "gap_policy": "D5.1 QUALITY_PROTOCOL.md: verified transitions <=10s; internal/reconnect <=5s; endpoints <=10s"
}

Legacy-format FINAL_DATA_QUALITY_REPORT.md is an intermediate metrics rendering; its legacy gap-policy prose does not describe D5.1. This separate report and frozen protocol are authoritative for this new experiment only.
