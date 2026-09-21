# D5.1 instrumentation smoke

{
  "protocol": "D5.1",
  "historical_D5_DATA_QUALITY": "FAIL",
  "D51_DATA_QUALITY": "PASS",
  "failures": [],
  "source_sha256": "e3c1faa37b23d4f02225d0471efd4f5fe0a8095841a0d4f3ce31ad4aa3f0fc7f",
  "source_stat_unchanged": true,
  "smoke_only": true,
  "statistical_D6_validation": false,
  "research_allowed": false,
  "paper_started": false,
  "replays": [
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
  ],
  "gap_policy": "D5.1 QUALITY_PROTOCOL.md: verified transitions <=10s; internal/reconnect <=5s; endpoints <=10s"
}

Legacy-format FINAL_DATA_QUALITY_REPORT.md is an intermediate metrics rendering; its legacy gap-policy prose does not describe D5.1. This separate report and frozen protocol are authoritative for this new experiment only.
