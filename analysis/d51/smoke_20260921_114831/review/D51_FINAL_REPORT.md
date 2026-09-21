# D5.1 instrumentation smoke

{
  "protocol": "D5.1",
  "historical_D5_DATA_QUALITY": "FAIL",
  "D51_DATA_QUALITY": "PASS",
  "failures": [],
  "source_sha256": "5b7e37193224e930302f6d9063dcabef597c44ad2b0c4e4869a90abab7d46ee4",
  "source_stat_unchanged": true,
  "smoke_only": true,
  "statistical_D6_validation": false,
  "research_allowed": false,
  "paper_started": false,
  "replays": [
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
  ],
  "gap_policy": "D5.1 QUALITY_PROTOCOL.md: verified transitions <=10s; internal/reconnect <=5s; endpoints <=10s"
}

Legacy-format FINAL_DATA_QUALITY_REPORT.md is an intermediate metrics rendering; its legacy gap-policy prose does not describe D5.1. This separate report and frozen protocol are authoritative for this new experiment only.
