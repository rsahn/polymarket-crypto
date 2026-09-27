"""Test 5h rotation, crash/recovery, redaction and non-overwrite for real calibration logging."""
import io, json, os, time, copy, threading
from pathlib import Path
from collections import namedtuple
from decimal import Decimal
import pytest
from analysis.d6.real_execution_calibration_v1.live_logging import LiveLog, LoggedJournal, REAL_CALIBRATION_ROTATION_SECONDS
from analysis.d6.real_execution_calibration_v1.core import Journal, digest
from analysis.d6.real_execution_calibration_v1.offline import sanitize, recover_prefix


def test_5h_rotation_artifact_and_log_files(tmp_path):
    """5h boundary: artifact + new log file; old log preserved; no overwrite."""
    now = [0.0]
    stream = io.StringIO()

    log = LiveLog(
        tmp_path, "test-exp-5h", console=stream,
        clock=lambda: now[0], background=False
    )
    log.snapshot = lambda: {"mode": "TEST", "clock": now[0], "seq": log.part}

    try:
        log.write({"kind": "INIT", "payload": {"version": "1"}})
        assert log.part == 0
        first_log = log.path

        # Advance just before 5h — no rotation
        now[0] = REAL_CALIBRATION_ROTATION_SECONDS - 0.01
        log.tick()
        assert log.part == 0
        assert log.path == first_log

        # Cross 5h boundary — rotation fires
        now[0] = REAL_CALIBRATION_ROTATION_SECONDS + 0.01
        log.tick()
        assert log.part == 1
        assert log.path != first_log

        # Check old log file preserved
        logs = sorted(tmp_path.glob("*.log"))
        assert len(logs) == 2  # old + new

        # Check 5H artifact was created with unique name (part + seconds in filename)
        artifacts = sorted(tmp_path.glob("*_5H.json"))
        assert len(artifacts) == 1
        artifact = json.loads(artifacts[0].read_text())
        assert artifact["mode"] == "TEST"
        assert artifact["seq"] == 0  # snapshot before part increment

        # Verify artifact filename contains part number for uniqueness
        assert f'_p{0:04d}_' in artifacts[0].name

        # Write to new part
        log.write({"kind": "INIT", "payload": {"version": "2"}})
        # Second rotation
        now[0] = REAL_CALIBRATION_ROTATION_SECONDS * 2 + 0.01
        log.tick()
        assert log.part == 2
        artifacts = sorted(tmp_path.glob("*_5H.json"))
        assert len(artifacts) == 2  # no overwrite
    finally:
        log.close()


def test_raw_journal_independent_from_log_rotation(tmp_path):
    """LoggedJournal .jsonl survives across log rotation boundaries."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "journal-survive", console=stream,
                  clock=lambda: now[0], background=False)
    try:
        journal = LoggedJournal(tmp_path / "test.jsonl", "journal-survive", log)
        journal.append("INIT", {"version": "test"})

        # Rotate the .log files twice
        now[0] = REAL_CALIBRATION_ROTATION_SECONDS + 0.01
        log.tick()
        journal.append("RECONCILED", {"CALIBRATION_ACCOUNT_RECONCILED": True})
        assert journal.seq == 2

        now[0] = REAL_CALIBRATION_ROTATION_SECONDS * 2 + 0.01
        log.tick()
        journal.append("STOP", {"reason": "TEST"})
        assert journal.seq == 3

        # .log files rotated 3x (initial + 2 rotations)
        assert len(list(tmp_path.glob("*.log"))) == 3

        # .jsonl journal is a single file, all 3 records present
        assert journal.path.exists()
        rows = list(Journal.read(journal.path))
        assert len(rows) == 3
        assert [r["kind"] for r in rows] == ["INIT", "RECONCILED", "STOP"]
    finally:
        log.close()


def test_no_overwrite_5h_artifact(tmp_path):
    """Artifact filenames are unique per rotation; never overwrite previous."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "no-overwrite", console=stream,
                  clock=lambda: now[0], background=False)
    log.snapshot = lambda: {"part": log.part, "clock": now[0]}
    try:
        now[0] = REAL_CALIBRATION_ROTATION_SECONDS + 0.01
        log.tick()
        now[0] = REAL_CALIBRATION_ROTATION_SECONDS * 2 + 0.01
        log.tick()
        artifacts = sorted(tmp_path.glob("*_5H.json"))
        assert len(artifacts) == 2
        assert artifacts[0].read_bytes() != artifacts[1].read_bytes()
        # Verify unique part numbers in filenames
        assert f'_p{0:04d}_' in artifacts[0].name
        assert f'_p{1:04d}_' in artifacts[1].name
        # Both artifacts contain valid JSON
        for a in artifacts:
            json.loads(a.read_text())
    finally:
        log.close()


def test_crash_raw_journal_recoverable(tmp_path):
    """Crash before 5h boundary: raw .jsonl journal fully recoverable."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "crash-recovery", console=stream,
                  clock=lambda: now[0], background=False)
    try:
        journal = LoggedJournal(tmp_path / "crash.jsonl", "crash-recovery", log)
        journal.append("INIT", {"version": "test"})
        journal.append("RESERVE", {"opportunity_id": "op1", "notional": "25", "fee_ceiling": "1"})
        journal.append("STOP", {"reason": "CRASH_TEST"})

        # Simulate crash: close journal, destroy log
        journal.close()
        log.close()

        # Recover from raw journal
        recovered = Journal.read(journal.path)
        rows = list(recovered)
        assert len(rows) == 3
        assert rows[0]["kind"] == "INIT"
        assert rows[2]["kind"] == "STOP"
        assert rows[2]["payload"]["reason"] == "CRASH_TEST"
    finally:
        try:
            journal.close()
        except Exception:
            pass
        try:
            log.close()
        except Exception:
            pass


def test_recover_prefix_stops_at_torn_tail(tmp_path):
    """recover_prefix handles torn tail without modifying original."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "torn-test", console=stream,
                  clock=lambda: now[0], background=False)
    try:
        journal = LoggedJournal(tmp_path / "torn.jsonl", "torn-test", log)
        journal.append("INIT", {"version": "1"})
        journal.append("RECONCILED", {"CALIBRATION_ACCOUNT_RECONCILED": True})
        journal.close()
        log.close()
        raw = journal.path.read_bytes()
        torn_path = tmp_path / "torn.jsonl"
        torn_path.write_bytes(raw + b'{"partial":')
        r = recover_prefix(torn_path)
        assert r["problem"] == "TORN_TAIL"
        assert r["verified_records"] == 2
        assert not r["resume_allowed"]
        assert r["STOP_NEW_ENTRIES"]
        # Original bytes unchanged
        assert torn_path.read_bytes() == raw + b'{"partial":'
    finally:
        try:
            journal.close()
        except Exception:
            pass
        try:
            log.close()
        except Exception:
            pass


def test_fsync_error_poisons_log(tmp_path, monkeypatch):
    """fsync failure prevents further writes."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "fsync-fail", console=stream,
                  clock=lambda: now[0], background=False)
    try:
        log.write({"kind": "INIT", "payload": {"version": "1"}})
        monkeypatch.setattr("os.fsync", lambda fd: (_ for _ in ()).throw(OSError("fixture")))
        with pytest.raises(OSError):
            log.write({"kind": "RECONCILED", "payload": {}})
        assert log.failed
    finally:
        log.close()


def test_secret_redaction_in_log(tmp_path):
    """Sensitive keys/values redacted via canonical_tree and artifact."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "redact-test", console=stream,
                  clock=lambda: now[0], background=False)
    log.snapshot = lambda: {"secret_key": "SHOULD_BE_REDACTED"}
    try:
        # Test canonical_tree directly (payload filtering happens before write)
        data = log.canonical_tree({
            "private-key": "canary_private",
            "nested": {"signature": "0xbadc0ffee"},
            "credential_field": "secret_sauce",
            "safe_field": "visible",
            "msg": "Bearer eyJhbGciOiJIUzI1NiJ9"
        })
        text = str(data)
        assert "canary_private" not in text
        assert "0xbadc0ffee" not in text
        assert "secret_sauce" not in text
        assert "visible" in text
        assert text.count("[REDACTED]") >= 3

        # Artifact snapshot also redacted via canonical_tree
        now[0] = REAL_CALIBRATION_ROTATION_SECONDS + 0.01
        log.tick()
        artifacts = sorted(tmp_path.glob("*_5H.json"))
        if artifacts:
            art = json.loads(artifacts[0].read_text())
            assert "SHOULD_BE_REDACTED" not in str(art)
            assert "[REDACTED]" in str(art)
    finally:
        log.close()


def test_aggregate_quota_enforced(tmp_path):
    """LiveLog max_bytes aggregate quota blocks writes when exceeded."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "quota-test", console=stream,
                  clock=lambda: now[0], background=False,
                  max_bytes=1)  # 1 byte = will be exceeded
    try:
        with pytest.raises(OSError, match="LOG_STORAGE_LIMIT|LOG_AGGREGATE_QUOTA"):
            log.write({"kind": "INIT", "payload": {"version": "1"}})
        assert log.failed
    finally:
        log.close()


def test_disk_low_fails(tmp_path, monkeypatch):
    """Disk space check in LiveLog.tick raises when free < 512MB."""
    DiskUsage = namedtuple("DiskUsage", ["free", "total", "used"])
    def low_usage(_path):
        return DiskUsage(512 * 1024**2 - 1, 0, 0)  # free below 512MB
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "disk-low", console=stream,
                  clock=lambda: now[0], background=False)
    try:
        monkeypatch.setattr("shutil.disk_usage", low_usage)
        with pytest.raises(OSError, match="LOG_DISK_LOW"):
            log.tick()
        assert log.failed
    finally:
        log.close()


def test_sanitize_freeform_strings():
    """sanitize catches bearer tokens, 0x64+ hex, and key=value secrets in strings."""
    payload = {
        "msg": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0",
        "hex": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "pkcs": "-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg",
        "env": "API_KEY=sk-1234",
        "safe": "hello world"
    }
    cleaned = sanitize(payload)
    for key in ("msg", "hex", "pkcs", "env"):
        assert cleaned[key] == "[REDACTED]", f"{key} was not redacted"
    assert cleaned["safe"] == "hello world"


def test_writer_lock_exclusive(tmp_path):
    """Only one LiveLog instance can write to a directory at a time."""
    log1 = LiveLog(tmp_path, "lock-test", console=io.StringIO(), background=False)
    try:
        with pytest.raises((PermissionError, OSError, Exception)):
            log2 = LiveLog(tmp_path, "lock-test", console=io.StringIO(), background=False)
            log2.close()
    finally:
        log1.close()


def test_close_after_failure_allows_recovery(tmp_path):
    """Even after log failure, the raw journal is readable."""
    now = [0.0]
    stream = io.StringIO()
    log = LiveLog(tmp_path, "post-fail", console=stream,
                  clock=lambda: now[0], background=False)
    try:
        journal = LoggedJournal(tmp_path / "post.jsonl", "post-fail", log)
        journal.append("INIT", {"version": "v1"})
        # Force log failure
        log.failed = True
        with pytest.raises(OSError, match="LOG_FAILED"):
            journal.append("STOP", {"reason": "after_fail"})
        journal.close()
        log.close()
        # Raw journal still readable — INIT was written before failure;
        # STOP was written to raw journal (Journal.append succeeded) but
        # .log write failed. Both records are present in the raw journal.
        rows = list(Journal.read(journal.path))
        assert len(rows) == 2
        assert rows[0]["kind"] == "INIT"
        assert rows[1]["kind"] == "STOP"
    finally:
        try:
            journal.close()
        except Exception:
            pass
        try:
            log.close()
        except Exception:
            pass
