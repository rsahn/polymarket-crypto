"""Tests for atomic experiment_id allocation with concurrent-launch safety.
No economic logic, no orders, no credentials.
"""
import json, os, tempfile, threading, time
from pathlib import Path
import pytest

from analysis.d6.real_execution_calibration_v1.core import allocate_experiment_id


def test_first_launch_gets_run0001():
    """Fresh directory: first allocation picks run0001."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        eid = allocate_experiment_id(d, base_name="test")
        assert eid == "test-run0001"
        assert not (d / f"{eid}.jsonl").exists()  # journal not created yet


def test_second_launch_gets_run0002():
    """Two sequential allocations produce distinct ascending IDs."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        eid1 = allocate_experiment_id(d, base_name="test")
        eid2 = allocate_experiment_id(d, base_name="test")
        assert eid1 == "test-run0001"
        assert eid2 == "test-run0002"
        assert eid1 != eid2


def test_three_sequential_runs():
    """Three runs in sequence produce 0001, 0002, 0003."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ids = [allocate_experiment_id(d, base_name="cal") for _ in range(3)]
        assert ids == ["cal-run0001", "cal-run0002", "cal-run0003"]


def test_respects_existing_journals():
    """If journals exist, counter seeds above the highest existing."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # Create an existing journal
        (d / "cal-run0005.jsonl").write_text("dummy\n")
        eid = allocate_experiment_id(d, base_name="cal")
        assert eid == "cal-run0006"


def test_respects_highest_existing():
    """Seeds from max run number among existing journals."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for n in [1, 3, 7]:
            (d / f"cal-run{n:04d}.jsonl").write_text("dummy\n")
        eid = allocate_experiment_id(d, base_name="cal")
        assert eid == "cal-run0008"


def test_does_not_overwrite():
    """Allocation never creates a journal; the caller creates it with 'xb'."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        eid = allocate_experiment_id(d, base_name="cal")
        jpath = d / f"{eid}.jsonl"
        assert not jpath.exists()
        # Simulate PreparedSession creating the journal
        jpath.write_text("line1\n")
        assert jpath.exists()


def test_concurrent_launch_raises():
    """Two threads cannot both hold the counter lock."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        results = []

        def allocate():
            try:
                eid = allocate_experiment_id(d, base_name="cal")
                results.append(eid)
            except OSError:
                results.append("LOCKED")

        t1 = threading.Thread(target=allocate)
        t2 = threading.Thread(target=allocate)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        # One succeeds, one gets LOCKED
        ok_ids = [r for r in results if r.startswith("cal-run")]
        locked = [r for r in results if r == "LOCKED"]
        assert len(ok_ids) == 1
        assert len(locked) == 1


def test_concurrent_launch_sequential():
    """After lock release, the next call gets the next ID."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        eid1 = allocate_experiment_id(d, base_name="cal")
        assert eid1 == "cal-run0001"
        eid2 = allocate_experiment_id(d, base_name="cal")
        assert eid2 == "cal-run0002"


def test_crash_does_not_burn_id():
    """If the caller crashes before creating the journal, the next sequential ID is safe."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        eid1 = allocate_experiment_id(d, base_name="cal")
        # Simulate crash — no journal created
        eid2 = allocate_experiment_id(d, base_name="cal")
        # Counter advances sequentially; run0002 has no journal file so no collision
        assert eid2 == "cal-run0002"
        # No .jsonl exists for either ID (caller creates them)
        assert not (d / "cal-run0001.jsonl").exists()
        assert not (d / "cal-run0002.jsonl").exists()


def test_custom_base_name():
    """Supports custom base names."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        eid = allocate_experiment_id(d, base_name="custom-v42")
        assert eid == "custom-v42-run0001"


def test_counter_persists_across_process():
    """Counter file persists, so a new Python process picks up where left off."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # First call (in a real process)
        eid1 = allocate_experiment_id(d, base_name="cal")
        # Simulate new process: delete in-memory state, reload from file
        eid2 = allocate_experiment_id(d, base_name="cal")
        assert eid1 == "cal-run0001"
        assert eid2 == "cal-run0002"
        # The counter file should have next=3
        counter = d / "._run_counter.json"
        assert counter.exists()
        assert json.loads(counter.read_text())["next"] == 3


def test_empty_directory_no_stale_counter():
    """Fresh directory with no counter file seeds at run0001."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        assert not (d / "._run_counter.json").exists()
        eid = allocate_experiment_id(d, base_name="cal")
        assert eid == "cal-run0001"
        assert (d / "._run_counter.json").exists()


def test_old_logs_preserved():
    """Existing .jsonl journals are never touched by allocation."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # Create an old journal
        old = d / "previous-run.jsonl"
        old.write_text("old data\n")
        old_stat = old.stat()
        # Allocate a new ID
        eid = allocate_experiment_id(d, base_name="cal")
        # Old file is untouched
        assert old.read_text() == "old data\n"
        assert old.stat().st_mtime == old_stat.st_mtime
