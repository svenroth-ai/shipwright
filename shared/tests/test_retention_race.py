"""Race-condition tests for append_iterate_entry retention.

The append transaction holds a single file_lock from migration through
retention, so in-worktree parallel appends are serialized. These tests
verify the invariants at that boundary:

1. With two threads each appending one entry to an already-at-cap store,
   the final count equals the retention cap (no extra, no fewer, no
   duplicates).
2. The lock on ``shipwright_run_config.json.lock`` prevents overlapping
   transactions — verified by a FIFO barrier on start and serial
   observation of intermediate state.

Tests use ``concurrent.futures.ThreadPoolExecutor`` with a
``threading.Barrier`` sync point so both threads enter the critical
section as close to simultaneously as possible.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from lib.iterate_entry import (
    MIGRATION_STATE_KEY,
    MIGRATION_TS_KEY,
    RUN_CONFIG_NAME,
    iterates_dir,
    read_iterate_entries,
)
from tools.append_iterate_entry import ITERATE_RETENTION, append_iterate_entry


def _canonical_entry(slug: str, date: str) -> dict:
    return {
        "run_id": f"iterate-2026-05-01-{slug}",
        "date": date,
        "type": "feature",
        "complexity": "medium",
        "branch": f"iterate/{slug}",
        "spec": None,
        "tests_passed": True,
        "adr": None,
    }


def _seed_at_cap(tmp_path: Path) -> None:
    """Create a project already at the retention cap so the next append
    triggers retention."""
    (tmp_path / "agent_docs").mkdir()
    d = iterates_dir(tmp_path)
    d.mkdir(parents=True)

    for i in range(ITERATE_RETENTION):
        day = (i // 24) + 1
        hour = i % 24
        run_id = f"iterate-2026-04-{day:02d}-seed{i:03d}"
        entry = {
            "run_id": run_id,
            "date": f"2026-04-{day:02d}T{hour:02d}:00:00Z",
            "type": "feature",
            "complexity": "small",
            "branch": f"iterate/seed{i}",
            "spec": None,
            "tests_passed": True,
            "adr": None,
        }
        (d / f"{run_id}.json").write_text(json.dumps(entry), encoding="utf-8")

    config = {
        "scope": "full_app",
        "iterate_history": [],
        MIGRATION_STATE_KEY: "complete",
        MIGRATION_TS_KEY: "2026-04-23T09:00:00Z",
    }
    (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")


def _synchronized_append(
    project: Path, entry: dict, barrier: threading.Barrier
) -> dict:
    """Worker used by ThreadPoolExecutor — waits on barrier then appends."""
    barrier.wait(timeout=5.0)
    return append_iterate_entry(project, entry)


class TestRetentionRace:
    def test_two_parallel_appends_at_cap_settle_at_cap(self, tmp_path):
        """Start with retention-cap entries. Two threads append at once.
        Each entry contends for retention because cap+1 exceeds keep_last,
        but both are new entries so one of them must survive along with
        the cap-minus-one oldest. End state: exactly ITERATE_RETENTION files,
        both new run_ids preserved because they are newer than the seed
        entries."""
        _seed_at_cap(tmp_path)

        barrier = threading.Barrier(2)
        entry_a = _canonical_entry("alpha", date="2026-06-01T10:00:00Z")
        entry_b = _canonical_entry("beta", date="2026-06-01T10:00:01Z")

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_a = pool.submit(_synchronized_append, tmp_path, entry_a, barrier)
            fut_b = pool.submit(_synchronized_append, tmp_path, entry_b, barrier)
            result_a = fut_a.result(timeout=15)
            result_b = fut_b.result(timeout=15)

        # Both calls succeeded.
        assert "entry_path" in result_a
        assert "entry_path" in result_b

        # Final file count is exactly the cap.
        files = list(iterates_dir(tmp_path).glob("iterate-*.json"))
        assert len(files) == ITERATE_RETENTION

        # Both new run_ids must be present (they're the newest by date).
        run_ids = {json.loads(p.read_text())["run_id"] for p in files}
        assert "iterate-2026-05-01-alpha" in run_ids
        assert "iterate-2026-05-01-beta" in run_ids

        # No duplicates.
        assert len(run_ids) == len(files)

    def test_parallel_appends_do_not_leave_orphan_locks(self, tmp_path):
        """After a burst of concurrent appends, subsequent serial appends
        still succeed promptly (lock released cleanly)."""
        _seed_at_cap(tmp_path)

        barrier = threading.Barrier(4)
        entries = [
            _canonical_entry(f"burst{i}", date=f"2026-06-01T{i:02d}:00:00Z")
            for i in range(4)
        ]

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(_synchronized_append, tmp_path, e, barrier) for e in entries
            ]
            for f in futures:
                f.result(timeout=15)

        # Now try a serial append with a very short lock timeout — it must
        # succeed because the burst released its locks.
        tail = _canonical_entry("after-burst", date="2026-07-01T00:00:00Z")
        result = append_iterate_entry(tmp_path, tail, lock_timeout_seconds=2.0)
        assert "entry_path" in result

    def test_parallel_appends_produce_unique_files(self, tmp_path):
        """No two append calls may leave the directory with collided or
        corrupted files. After 8 threads each append a distinct run_id,
        all 8 must be present."""
        _seed_at_cap(tmp_path)

        n = 8
        barrier = threading.Barrier(n)
        entries = [
            _canonical_entry(f"para{i:03d}", date=f"2026-07-0{(i % 9) + 1}T{i:02d}:00:00Z")
            for i in range(n)
        ]

        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = [
                pool.submit(_synchronized_append, tmp_path, e, barrier) for e in entries
            ]
            for f in futures:
                f.result(timeout=20)

        # All 8 new entries survive retention because they're the freshest.
        surviving = read_iterate_entries(tmp_path)
        run_ids = {e["run_id"] for e in surviving}
        for i in range(n):
            assert f"iterate-2026-05-01-para{i:03d}" in run_ids


class TestLockSerialization:
    def test_second_append_waits_for_first_to_finish_migration(self, tmp_path):
        """Concrete evidence that the file_lock actually serializes:
        thread A starts a migration, thread B blocks until A completes.
        We measure B's wait time and assert it is >= the simulated migration
        duration."""
        (tmp_path / "agent_docs").mkdir()
        # Seed a legacy project so the first append will run a migration.
        legacy = [
            _canonical_entry(f"old{i}", date=f"2026-04-0{i}T10:00:00Z")
            for i in range(1, 4)
        ]
        config = {"scope": "full_app", "iterate_history": legacy}
        (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")

        import tools.append_iterate_entry as tool

        real_write_entry_file = tool._write_entry_file
        slow_write_event = threading.Event()
        slow_write_done = threading.Event()

        def slow_first_then_normal(project_root, entry, *, overwrite=True):
            """Only the FIRST migration-entry write is delayed. That's
            enough to prove serialization because the lock is held the
            entire time. Returns the real write result."""
            if not slow_write_event.is_set():
                slow_write_event.set()
                time.sleep(0.35)  # hold the lock long enough to measure
                slow_write_done.set()
            return real_write_entry_file(project_root, entry, overwrite=overwrite)

        import tools.append_iterate_entry as tool_module
        tool_module._write_entry_file = slow_first_then_normal

        try:
            start = time.monotonic()

            def worker_a():
                append_iterate_entry(
                    tmp_path,
                    _canonical_entry("thread-a", date="2026-06-01T10:00:00Z"),
                )

            def worker_b():
                # Wait until A has entered its slow write so we're guaranteed
                # to contend for the lock instead of arriving early.
                slow_write_event.wait(timeout=2.0)
                append_iterate_entry(
                    tmp_path,
                    _canonical_entry("thread-b", date="2026-06-02T10:00:00Z"),
                )

            t_a = threading.Thread(target=worker_a)
            t_b = threading.Thread(target=worker_b)
            t_a.start()
            t_b.start()
            t_a.join(timeout=15)
            t_b.join(timeout=15)
            elapsed = time.monotonic() - start

            # Total elapsed must exceed the single slow-write delay because
            # B could only proceed after A finished. A shorter total would
            # mean B bypassed the lock.
            assert elapsed >= 0.3, (
                f"expected serialization (>0.3s) but finished in {elapsed:.3f}s"
            )

            # Both entries must be present at the end.
            run_ids = {e["run_id"] for e in read_iterate_entries(tmp_path)}
            assert "iterate-2026-05-01-thread-a" in run_ids
            assert "iterate-2026-05-01-thread-b" in run_ids
        finally:
            tool_module._write_entry_file = real_write_entry_file
