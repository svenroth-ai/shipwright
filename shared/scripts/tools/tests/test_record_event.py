"""Tests for record_event.py — event writer and reader."""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

# Ensure shared scripts are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.record_event import (
    append_event,
    build_event,
    generate_event_id,
    has_commit,
    has_phase_event,
    main as record_main,
    parse_args,
    read_events,
)
from scripts.lib.config import apply_amendments, read_events as config_read_events


@pytest.fixture
def project(tmp_path):
    """Provide a temp project root."""
    return tmp_path


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

class TestGenerateEventId:
    def test_format(self):
        eid = generate_event_id()
        assert eid.startswith("evt-")
        assert len(eid) == 12  # evt- + 8 hex

    def test_unique(self):
        ids = {generate_event_id() for _ in range(1000)}
        assert len(ids) == 1000


# ---------------------------------------------------------------------------
# Append + Read round-trip
# ---------------------------------------------------------------------------

class TestAppendAndRead:
    def test_basic_roundtrip(self, project):
        event = {"v": 1, "id": "evt-test0001", "ts": "2026-01-01T00:00:00Z",
                 "type": "phase_started", "phase": "project"}
        append_event(project, event)

        events = read_events(project)
        assert len(events) == 1
        assert events[0]["id"] == "evt-test0001"
        assert events[0]["type"] == "phase_started"

    def test_multiple_events(self, project):
        for i in range(5):
            event = {"v": 1, "id": f"evt-{i:08x}", "ts": "2026-01-01T00:00:00Z",
                     "type": "phase_completed", "phase": "project"}
            append_event(project, event)

        events = read_events(project)
        assert len(events) == 5

    def test_read_empty_dir(self, project):
        events = read_events(project)
        assert events == []


# ---------------------------------------------------------------------------
# Corruption tolerance
# ---------------------------------------------------------------------------

class TestCorruptionTolerance:
    def test_corrupt_line_skipped(self, project):
        path = project / "shipwright_events.jsonl"
        path.write_text(
            '{"v":1,"id":"evt-good0001","ts":"T","type":"phase_started","phase":"p"}\n'
            'THIS IS NOT JSON\n'
            '{"v":1,"id":"evt-good0002","ts":"T","type":"phase_completed","phase":"p"}\n',
            encoding="utf-8",
        )
        with pytest.warns(match="Corrupt event at line 2"):
            events = read_events(project)
        assert len(events) == 2
        assert events[0]["id"] == "evt-good0001"
        assert events[1]["id"] == "evt-good0002"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_has_commit_true(self, project):
        event = {"v": 1, "id": "evt-test0001", "ts": "T",
                 "type": "work_completed", "source": "build", "commit": "abc123"}
        append_event(project, event)
        assert has_commit(project, "abc123") is True

    def test_has_commit_false(self, project):
        assert has_commit(project, "nonexistent") is False

    def test_dedup_via_cli(self, project):
        # First write
        result = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "build", "--commit", "abc123",
            "--tests-passed", "5", "--tests-total", "5",
            "--affected-frs", "FR-01.01",
        ])
        assert result == 0
        assert len(read_events(project)) == 1

        # Second write with dedup flag — should skip
        result = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "build", "--commit", "abc123",
            "--tests-passed", "5", "--tests-total", "5",
            "--affected-frs", "FR-01.01",
            "--deduplicate-by-commit",
        ])
        assert result == 0
        assert len(read_events(project)) == 1  # Still 1

    def test_has_phase_event_true(self, project):
        event = {"v": 1, "id": "evt-phase01", "ts": "T",
                 "type": "phase_completed", "phase": "project"}
        append_event(project, event)
        assert has_phase_event(project, "project") is True

    def test_has_phase_event_false(self, project):
        assert has_phase_event(project, "project") is False

    def test_phase_completed_dedup(self, project):
        """Second phase_completed for same phase is automatically skipped."""
        # First write
        result = record_main([
            "--project-root", str(project),
            "--type", "phase_completed",
            "--phase", "project",
            "--detail", "3 splits created",
        ])
        assert result == 0
        assert len(read_events(project)) == 1

        # Second write — should be skipped (same phase)
        result = record_main([
            "--project-root", str(project),
            "--type", "phase_completed",
            "--phase", "project",
        ])
        assert result == 0
        assert len(read_events(project)) == 1  # Still 1

    def test_phase_completed_different_phases_not_deduped(self, project):
        """phase_completed for different phases are NOT deduped."""
        record_main([
            "--project-root", str(project),
            "--type", "phase_completed", "--phase", "project",
        ])
        record_main([
            "--project-root", str(project),
            "--type", "phase_completed", "--phase", "plan",
        ])
        assert len(read_events(project)) == 2


# ---------------------------------------------------------------------------
# Event building
# ---------------------------------------------------------------------------

class TestBuildEvent:
    def test_work_completed_build(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "work_completed",
            "--source", "build",
            "--split", "01-foundation",
            "--section", "01-project-setup",
            "--commit", "abc123",
            "--tests-passed", "5", "--tests-total", "5",
            "--review-type", "self-review",
            "--review-findings", "0", "--review-fixed", "0",
            "--affected-frs", "FR-01.01,FR-01.02",
        ])
        event = build_event(args)
        assert event["v"] == 1
        assert event["type"] == "work_completed"
        assert event["source"] == "build"
        assert event["split"] == "01-foundation"
        assert event["tests"] == {"passed": 5, "total": 5}
        assert event["review"] == {"type": "self-review", "findings": 0, "fixed": 0}
        assert event["affected_frs"] == ["FR-01.01", "FR-01.02"]

    def test_work_completed_iterate(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "feature",
            "--description", "Add filtering",
            "--commit", "def456",
            "--tests-new", "3", "--tests-passed", "47", "--tests-total", "47",
            "--affected-frs", "FR-02.08",
            "--new-frs", "FR-02.08",
            "--adr-id", "ADR-055",
        ])
        event = build_event(args)
        assert event["source"] == "iterate"
        assert event["intent"] == "feature"
        assert event["tests"] == {"new": 3, "passed": 47, "total": 47}
        assert event["new_frs"] == ["FR-02.08"]
        assert event["adr_id"] == "ADR-055"

    def test_task_created_minimal(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "task_created",
            "--description", "Fix auth redirect bug",
        ])
        event = build_event(args)
        assert event["type"] == "task_created"
        assert event["description"] == "Fix auth redirect bug"
        assert "intent" not in event
        assert "priority" not in event

    def test_task_created_full(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "task_created",
            "--description", "Add search feature",
            "--intent", "feature",
            "--priority", "high",
        ])
        event = build_event(args)
        assert event["type"] == "task_created"
        assert event["description"] == "Add search feature"
        assert event["intent"] == "feature"
        assert event["priority"] == "high"

    def test_phase_completed(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "phase_completed",
            "--phase", "build",
        ])
        event = build_event(args)
        assert event["type"] == "phase_completed"
        assert event["phase"] == "build"
        assert "detail" not in event

    def test_phase_completed_with_detail(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "phase_completed",
            "--phase", "deploy",
            "--detail", "https://dev-app.jpc.infomaniak.com",
        ])
        event = build_event(args)
        assert event["type"] == "phase_completed"
        assert event["phase"] == "deploy"
        assert event["detail"] == "https://dev-app.jpc.infomaniak.com"

    def test_test_run(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "test_run",
            "--trigger", "phase:test",
            "--unit-passed", "833", "--unit-total", "833",
            "--e2e-passed", "43", "--e2e-total", "55",
            "--smoke-status", "pass",
        ])
        event = build_event(args)
        assert event["layers"]["unit"] == {"passed": 833, "total": 833}
        assert event["layers"]["e2e"] == {"passed": 43, "total": 55}
        assert event["layers"]["smoke"] == {"status": "pass"}

    def test_event_amended(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "event_amended",
            "--amends", "evt-a1f0",
            "--fields", '{"affected_frs": ["FR-01.01", "FR-01.02"]}',
        ])
        event = build_event(args)
        assert event["amends"] == "evt-a1f0"
        assert event["fields"]["affected_frs"] == ["FR-01.01", "FR-01.02"]


# ---------------------------------------------------------------------------
# Amendments via config.py
# ---------------------------------------------------------------------------

class TestAmendments:
    def test_apply_amendments(self, project):
        events = [
            {"v": 1, "id": "evt-orig", "ts": "T", "type": "work_completed",
             "source": "build", "affected_frs": ["FR-01.01"]},
            {"v": 1, "id": "evt-fix", "ts": "T2", "type": "event_amended",
             "amends": "evt-orig", "fields": {"affected_frs": ["FR-01.01", "FR-01.02"]}},
        ]
        result = apply_amendments(events)
        assert len(result) == 1
        assert result[0]["affected_frs"] == ["FR-01.01", "FR-01.02"]
        assert result[0]["id"] == "evt-orig"


# ---------------------------------------------------------------------------
# Concurrency (file-lock safety)
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_parallel_writes_no_data_loss(self, project):
        """5 threads write 100 events each — all 500 must survive."""
        def write_batch(thread_id: int):
            for i in range(100):
                event = {
                    "v": 1,
                    "id": generate_event_id(),
                    "ts": "2026-01-01T00:00:00Z",
                    "type": "work_completed",
                    "source": "build",
                    "commit": f"t{thread_id}-{i:03d}",
                }
                append_event(project, event)

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(write_batch, t) for t in range(5)]
            for f in futures:
                f.result()

        events = read_events(project)
        assert len(events) == 500

        # All IDs unique
        ids = [e["id"] for e in events]
        assert len(set(ids)) == 500

        # All lines valid JSON
        path = project / "shipwright_events.jsonl"
        for line in path.open("r", encoding="utf-8"):
            line = line.strip()
            if line:
                json.loads(line)  # Should not raise


# ---------------------------------------------------------------------------
# config.py read_events integration
# ---------------------------------------------------------------------------

class TestConfigReadEvents:
    def test_reads_same_as_record_event(self, project):
        event = {"v": 1, "id": "evt-cfg01", "ts": "T", "type": "phase_started", "phase": "project"}
        append_event(project, event)

        events = config_read_events(project)
        assert len(events) == 1
        assert events[0]["id"] == "evt-cfg01"
