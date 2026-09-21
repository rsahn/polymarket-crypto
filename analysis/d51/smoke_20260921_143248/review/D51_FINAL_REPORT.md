# D5.1 instrumentation smoke

{
  "protocol": "D5.1",
  "historical_D5_DATA_QUALITY": "FAIL",
  "D51_DATA_QUALITY": "PASS",
  "failures": [],
  "source_sha256": "d9cd47007c7fc4e702d85e27bfb520c522512e5e49d7789690ae9c0e7693fc87",
  "source_stat_unchanged": true,
  "smoke_only": true,
  "statistical_D6_validation": false,
  "research_allowed": false,
  "paper_started": false,
  "replays": [
    {
      "replay": 1,
      "event_count": 1400618,
      "decision_sha256": "1e1b559a6d586d717a4f3034b495c2574f6edc34fc27f0c44242f85b2f41677c",
      "result_sha256": "9c98f4bf1f8db560b3dd63545855db725639b4489aa558d520409e5e7297fa54"
    },
    {
      "replay": 2,
      "event_count": 1400618,
      "decision_sha256": "1e1b559a6d586d717a4f3034b495c2574f6edc34fc27f0c44242f85b2f41677c",
      "result_sha256": "9c98f4bf1f8db560b3dd63545855db725639b4489aa558d520409e5e7297fa54"
    }
  ],
  "gap_policy": "D5.1 QUALITY_PROTOCOL.md: verified transitions <=10s; internal/reconnect <=5s; endpoints <=10s"
}

Legacy-format FINAL_DATA_QUALITY_REPORT.md is an intermediate metrics rendering; its legacy gap-policy prose does not describe D5.1. This separate report and frozen protocol are authoritative for this new experiment only.
