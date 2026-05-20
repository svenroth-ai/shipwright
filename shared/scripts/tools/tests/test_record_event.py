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

    def test_work_completed_change_type(self):
        """change_type and none_reason are captured when --change-type is passed."""
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "bug",
            "--description", "Cross-platform test stub fix",
            "--commit", "abc1234",
            "--tests-passed", "5", "--tests-total", "5",
            "--change-type", "tooling",
            "--none-reason", "Test-infra fix, no FR touched",
        ])
        event = build_event(args)
        assert event["change_type"] == "tooling"
        assert event["none_reason"] == "Test-infra fix, no FR touched"
        # No affected_frs is fine — Iterate C.1 will gate this combination.
        assert "affected_frs" not in event

    def test_work_completed_change_type_absent_by_default(self):
        """change_type/none_reason are omitted when not passed (backward-compat)."""
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "feature",
            "--description", "Add filtering",
            "--commit", "def4567",
            "--tests-passed", "47", "--tests-total", "47",
            "--affected-frs", "FR-02.08",
        ])
        event = build_event(args)
        assert "change_type" not in event
        assert "none_reason" not in event

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


# ---------------------------------------------------------------------------
# E spec MEDIUM-D1 — --changed-files support
# ---------------------------------------------------------------------------


class TestChangedFiles:
    """`--changed-files` records the files actually changed in the commit.

    Required by D's drift-detection (`is_io_boundary_change`) and HIGH-5's
    round-trip heuristic scoping. Without this field, downstream tools
    fall back to weaker text heuristics.
    """

    def test_comma_separated_changed_files(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "abc1234",
            "--description", "Test changed-files",
            "--changed-files", ".env,shipwright_run_config.json,src/x.py",
        ])
        assert rc == 0
        events = read_events(project)
        assert len(events) == 1
        assert events[0]["changed_files"] == [
            ".env", "shipwright_run_config.json", "src/x.py",
        ]

    def test_json_array_changed_files(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "abc1235",
            "--changed-files", '[".env", "src/y.py"]',
        ])
        assert rc == 0
        events = read_events(project)
        assert events[0]["changed_files"] == [".env", "src/y.py"]

    def test_changed_files_normalizes_backslashes(self, project):
        """Windows path output from `git diff` may use backslashes — normalize."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "build", "--commit", "abc1236",
            "--changed-files", "src\\foo.py,tests\\bar.py",
        ])
        assert rc == 0
        events = read_events(project)
        assert events[0]["changed_files"] == ["src/foo.py", "tests/bar.py"]

    def test_changed_files_empty_handled(self, project):
        """Empty string → no `changed_files` key on the event."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "abc1237",
        ])
        assert rc == 0
        events = read_events(project)
        assert "changed_files" not in events[0]


# ---------------------------------------------------------------------------
# Worktree-aware event-log resolution
#
# Under /shipwright-iterate worktree isolation the event log is a
# repo-scoped journal. A literal project_root/EVENT_FILE from inside an
# ephemeral worktree writes a throwaway copy discarded on `git worktree
# remove` — record_event must resolve the MAIN repo's log instead.
# ---------------------------------------------------------------------------

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(cwd: Path, *args: str) -> None:
    import subprocess
    subprocess.run(
        ["git", *args], cwd=str(cwd), env=_GIT_ENV,
        capture_output=True, text=True, check=True,
    )


def _init_main_repo(tmp_path: Path) -> Path:
    """A git repo with one commit. Returns the main working tree."""
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-b", "main")
    (main / "README.md").write_text("x\n", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-m", "init")
    return main


def _add_worktree(main: Path, slug: str) -> Path:
    """Add a linked worktree under <main>/.worktrees/<slug>."""
    wt = main / ".worktrees" / slug
    _git(main, "worktree", "add", str(wt), "-b", f"iterate/{slug}", "main")
    return wt


class TestWorktreeAwareLog:
    """record_event + config.read_events resolve the MAIN repo's event log
    from inside a linked git worktree."""

    def test_append_event_from_worktree_lands_in_main_log(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(wt, {"v": 1, "id": "evt-wt000001", "ts": "T",
                           "type": "work_completed", "source": "iterate",
                           "commit": "c0ffee0"})
        # Lands in the MAIN repo's log — survives `git worktree remove`.
        assert (main / "shipwright_events.jsonl").exists()
        assert not (wt / "shipwright_events.jsonl").exists()
        assert [e["id"] for e in read_events(main)] == ["evt-wt000001"]

    def test_read_events_from_worktree_reads_main_log(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(main, {"v": 1, "id": "evt-main00001", "ts": "T",
                            "type": "phase_started", "phase": "build"})
        assert [e["id"] for e in read_events(wt)] == ["evt-main00001"]

    def test_lock_file_sits_next_to_main_log(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(wt, {"v": 1, "id": "evt-lock00001", "ts": "T",
                          "type": "phase_started", "phase": "build"})
        # The mutex must guard the main log, not a throwaway worktree lock.
        assert (main / "shipwright_events.jsonl.lock").exists()
        assert not (wt / "shipwright_events.jsonl.lock").exists()

    def test_has_commit_dedup_sees_main_log_from_worktree(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(main, {"v": 1, "id": "evt-dd000001", "ts": "T",
                            "type": "work_completed", "source": "iterate",
                            "commit": "deadbee"})
        assert has_commit(wt, "deadbee") is True
        assert has_commit(wt, "absent0") is False

    def test_script_invocation_from_worktree_lands_in_main_log(self, tmp_path):
        """The argparse CLI path (record_main) is worktree-aware too —
        covers script-mode invocation, not only in-process import."""
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        rc = record_main([
            "--project-root", str(wt),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "5cr1pt0",
            "--description", "from worktree via CLI",
        ])
        assert rc == 0
        assert [e["commit"] for e in read_events(main)] == ["5cr1pt0"]
        assert not (wt / "shipwright_events.jsonl").exists()

    def test_two_worktrees_concurrent_append_share_one_main_log(self, tmp_path):
        """Two worktrees appending concurrently funnel into ONE main log;
        the centralized lock serializes them with no data loss."""
        main = _init_main_repo(tmp_path)
        wt_a = _add_worktree(main, "wt-a")
        wt_b = _add_worktree(main, "wt-b")

        def write_batch(wt: Path, tag: str) -> None:
            for i in range(25):
                append_event(wt, {
                    "v": 1, "id": generate_event_id(), "ts": "T",
                    "type": "work_completed", "source": "iterate",
                    "commit": f"{tag}-{i:02d}",
                })

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write_batch, wt_a, "a"),
                       pool.submit(write_batch, wt_b, "b")]
            for f in futures:
                f.result()

        events = read_events(main)
        assert len(events) == 50
        assert len({e["id"] for e in events}) == 50
        assert not (wt_a / "shipwright_events.jsonl").exists()
        assert not (wt_b / "shipwright_events.jsonl").exists()

    def test_config_read_events_from_worktree_reads_main_log(self, tmp_path):
        """config.read_events (the dashboard's event source) is worktree-aware."""
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(main, {"v": 1, "id": "evt-cfgwt001", "ts": "T",
                            "type": "work_completed", "source": "iterate",
                            "commit": "x"})
        assert [e["id"] for e in config_read_events(wt)] == ["evt-cfgwt001"]

    def test_non_git_dir_behavior_unchanged(self, tmp_path):
        """Regression guard: in a non-git dir the log stays at
        project_root/EVENT_FILE — no behavior change for plain projects."""
        append_event(tmp_path, {"v": 1, "id": "evt-plain0001", "ts": "T",
                                "type": "phase_started", "phase": "build"})
        assert (tmp_path / "shipwright_events.jsonl").exists()
        assert read_events(tmp_path)[0]["id"] == "evt-plain0001"

    def test_changed_files_omitted_argument(self, project):
        """Argument absent → field absent (backwards compat)."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "build", "--commit", "abc1238",
            "--description", "no flag passed",
        ])
        assert rc == 0
        events = read_events(project)
        assert "changed_files" not in events[0]

    def test_changed_files_round_trip_with_is_io_boundary_change(self, project):
        """The field is consumable by `is_io_boundary_change` (full chain)."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "abc1239",
            "--changed-files", ".env.local,src/parser.py",
        ])
        assert rc == 0
        events = read_events(project)
        files = events[0]["changed_files"]

        # Import is_io_boundary_change from the iterate plugin.
        from importlib.util import spec_from_file_location, module_from_spec
        repo_root = Path(__file__).resolve().parents[4]
        cc_path = (
            repo_root / "plugins" / "shipwright-iterate"
            / "scripts" / "lib" / "classify_complexity.py"
        )
        spec = spec_from_file_location("classify_complexity", cc_path)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.is_io_boundary_change(files) is True


# ---------------------------------------------------------------------------
# Spec-impact classification gate (iterate-2026-05-16-spec-impact-gate)
#
# Every FEATURE/CHANGE iterate work_completed event must name the FRs it
# touched (--affected-frs / --new-frs) OR record --spec-impact none with a
# justification. record_event.py fails closed (exit 1) otherwise. Build
# events and intent-less / bug-intent iterate events are unaffected.
# ---------------------------------------------------------------------------


class TestSpecImpactField:
    """build_event records the spec_impact classification onto the event."""

    def test_spec_impact_and_justification_recorded(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "work_completed",
            "--source", "iterate", "--intent", "change", "--commit", "c1",
            "--description", "refactor internals",
            "--spec-impact", "none",
            "--spec-impact-justification", "behavior-preserving internal refactor",
        ])
        event = build_event(args)
        assert event["spec_impact"] == "none"
        assert event["spec_impact_justification"] == (
            "behavior-preserving internal refactor"
        )

    def test_spec_impact_absent_when_not_passed(self):
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "work_completed",
            "--source", "build", "--commit", "c2",
        ])
        event = build_event(args)
        assert "spec_impact" not in event
        assert "spec_impact_justification" not in event


class TestSpecImpactGate:
    """record_event.main fails closed on an unclassified feature/change iterate."""

    def test_feature_with_affected_frs_passes(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "feature", "--commit", "g1",
            "--description", "add endpoint",
            "--spec-impact", "add", "--affected-frs", "FR-01.05",
        ])
        assert rc == 0
        assert len(read_events(project)) == 1

    def test_feature_with_new_frs_only_passes(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "feature", "--commit", "g2",
            "--description", "add endpoint",
            "--spec-impact", "add", "--new-frs", "FR-01.06",
        ])
        assert rc == 0

    def test_feature_without_frs_fails(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "feature", "--commit", "g3",
            "--description", "add endpoint, forgot the FR",
        ])
        assert rc == 1
        assert read_events(project) == []  # fail-closed: nothing written

    def test_change_without_frs_fails(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "change", "--commit", "g4",
            "--description", "modify behavior",
            "--spec-impact", "modify",
        ])
        assert rc == 1

    def test_spec_impact_none_without_justification_fails(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "feature", "--commit", "g5",
            "--description", "claims no spec impact",
            "--spec-impact", "none",
        ])
        assert rc == 1
        assert read_events(project) == []

    def test_spec_impact_none_with_justification_passes(self, project):
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "change", "--commit", "g6",
            "--description", "internal refactor",
            "--spec-impact", "none",
            "--spec-impact-justification", "no user-visible behavior change",
        ])
        assert rc == 0
        assert len(read_events(project)) == 1

    def test_build_event_without_frs_unaffected(self, project):
        """Build events are NOT gated — only iterate feature/change."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "build", "--commit", "g7", "--section", "01-x",
        ])
        assert rc == 0

    def test_bug_intent_without_frs_unaffected(self, project):
        """BUG iterates are not gated — a bug fix need not touch the spec."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "bug", "--commit", "g8",
            "--description", "fix crash",
        ])
        assert rc == 0

    def test_intentless_iterate_event_unaffected(self, project):
        """An iterate event with no --intent is not gated (backwards compat)."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "g9",
            "--description", "legacy-style event",
        ])
        assert rc == 0
