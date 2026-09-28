# D5.1 instrumentation smoke

{
  "protocol": "D5.1",
  "historical_D5_DATA_QUALITY": "FAIL",
  "D51_DATA_QUALITY": "FAIL",
  "failures": [
    "ACCEPTED_AFTER_COLLECTION_STOP",
    "RECONNECT_GAP_OVER_5S"
  ],
  "source_sha256": "4d3a57c162b8db5974d0d5060f43732eab523248aef938049ee3c5e256374a25",
  "source_stat_unchanged": true,
  "smoke_only": true,
  "statistical_D6_validation": false,
  "research_allowed": false,
  "paper_started": false,
  "replays": [
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
  ],
  "gap_policy": "D5.1 QUALITY_PROTOCOL.md: verified transitions <=10s; internal/reconnect <=5s; endpoints <=10s"
}

Legacy-format FINAL_DATA_QUALITY_REPORT.md is an intermediate metrics rendering; its legacy gap-policy prose does not describe D5.1. This separate report and frozen protocol are authoritative for this new experiment only.
