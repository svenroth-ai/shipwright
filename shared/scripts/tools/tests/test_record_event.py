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
        with pytest.warns(match=r"Corrupt event at shipwright_events\.jsonl:2"):
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

    def test_has_phase_event_split_id_matched(self, project):
        """has_phase_event keys on (phase, splitId): matches only the same split."""
        append_event(project, {"v": 1, "id": "evt-split001", "ts": "T",
                               "type": "phase_completed", "phase": "build",
                               "splitId": "01-foundation"})
        assert has_phase_event(project, "build", "01-foundation") is True
        # Different split → not a duplicate.
        assert has_phase_event(project, "build", "02-ui") is False
        # phase-only lookup (splitId=None) does not match a split-tagged event.
        assert has_phase_event(project, "build") is False

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

    def test_phase_completed_different_splits_not_deduped(self, project):
        """AC1 — same phase, different splitId: ALL ends persist (per-split).

        A multi-split build phase records one phase_completed per split, so the
        WebUI PhaseRail can show per-split bars and derive the full phase span.
        """
        for split in ("01-foundation", "02-ui", "03-api"):
            record_main([
                "--project-root", str(project),
                "--type", "phase_completed", "--phase", "build",
                "--split-id", split,
            ])
        events = read_events(project)
        assert len(events) == 3
        assert {e.get("splitId") for e in events} == {"01-foundation", "02-ui", "03-api"}

    def test_phase_completed_same_split_deduped(self, project):
        """AC2 — same (phase, splitId): the second is skipped (crash-resume backstop)."""
        record_main([
            "--project-root", str(project),
            "--type", "phase_completed", "--phase", "build",
            "--split-id", "01-foundation",
        ])
        record_main([
            "--project-root", str(project),
            "--type", "phase_completed", "--phase", "build",
            "--split-id", "01-foundation",
        ])
        assert len(read_events(project)) == 1  # second (same split) skipped


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

    def test_phase_completed_no_split_id_omits_field(self):
        """AC2 back-compat — no --split-id → no top-level splitId key."""
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "phase_completed", "--phase", "build",
        ])
        event = build_event(args)
        assert "splitId" not in event

    def test_phase_event_split_id_top_level(self):
        """AC3 — --split-id promotes splitId to a first-class phase-event field."""
        for event_type in ("phase_started", "phase_completed", "phase_failed"):
            args = parse_args([
                "--project-root", "/tmp",
                "--type", event_type, "--phase", "build",
                "--split-id", "02-ui",
            ])
            event = build_event(args)
            assert event["splitId"] == "02-ui", event_type

    def test_phase_event_explicit_empty_split_id_preserved(self):
        """An explicitly-supplied splitId is forwarded on an `is not None` basis
        (not truthiness), so a falsey-but-explicit value is not silently dropped
        into phase-only dedup (external-review hardening)."""
        args = parse_args([
            "--project-root", "/tmp",
            "--type", "phase_completed", "--phase", "build",
            "--split-id", "",
        ])
        event = build_event(args)
        assert event["splitId"] == ""  # kept as a distinct key, not omitted

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
            "--change-type", "tooling", "--none-reason", "test-infra: changed-files capture",
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
            "--change-type", "tooling", "--none-reason", "test-infra: changed-files capture",
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
            "--change-type", "tooling", "--none-reason", "test-infra: changed-files capture",
        ])
        assert rc == 0
        events = read_events(project)
        assert "changed_files" not in events[0]


# ---------------------------------------------------------------------------
# Per-tree event-log resolution (iterate-2026-05-29-events-jsonl-worktree-commit)
#
# The event log is a per-tree, PR-committed artifact: from inside a
# /shipwright-iterate worktree, record_event writes the WORKTREE's own
# shipwright_events.jsonl (which F6 commits and the PR carries to main) — NOT
# the main repo's log. The main tree is never touched by an iterate.
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
    """record_event + config.read_events operate on the WORKTREE's own event
    log from inside a linked git worktree (per-tree, PR-committed model)."""

    def test_append_event_from_worktree_lands_in_worktree_log(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(wt, {"v": 1, "id": "evt-wt000001", "ts": "T",
                           "type": "work_completed", "source": "iterate",
                           "commit": "c0ffee0"})
        # Lands in the WORKTREE's own log (F6 commits it; ships in the PR).
        # The main tree is never written.
        assert (wt / "shipwright_events.jsonl").exists()
        assert not (main / "shipwright_events.jsonl").exists()
        assert [e["id"] for e in read_events(wt)] == ["evt-wt000001"]

    def test_read_events_from_worktree_reads_worktree_log(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(wt, {"v": 1, "id": "evt-wtread001", "ts": "T",
                          "type": "phase_started", "phase": "build"})
        assert [e["id"] for e in read_events(wt)] == ["evt-wtread001"]

    def test_lock_file_sits_next_to_worktree_log(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(wt, {"v": 1, "id": "evt-lock00001", "ts": "T",
                          "type": "phase_started", "phase": "build"})
        # The mutex guards the worktree's own log, next to where it's written.
        assert (wt / "shipwright_events.jsonl.lock").exists()
        assert not (main / "shipwright_events.jsonl.lock").exists()

    def test_has_commit_dedup_sees_worktree_log(self, tmp_path):
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(wt, {"v": 1, "id": "evt-dd000001", "ts": "T",
                          "type": "work_completed", "source": "iterate",
                          "commit": "deadbee"})
        assert has_commit(wt, "deadbee") is True
        assert has_commit(wt, "absent0") is False

    def test_script_invocation_from_worktree_lands_in_worktree_log(self, tmp_path):
        """The argparse CLI path (record_main) is per-tree too — covers
        script-mode invocation, not only in-process import."""
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        rc = record_main([
            "--project-root", str(wt),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "5cr1pt0",
            "--description", "from worktree via CLI",
            # ADR-059 FR-gate: an iterate work_completed event must classify.
            "--change-type", "tooling", "--none-reason", "worktree-log CLI test",
        ])
        assert rc == 0
        assert [e["commit"] for e in read_events(wt)] == ["5cr1pt0"]
        assert not (main / "shipwright_events.jsonl").exists()

    def test_two_worktrees_append_to_independent_logs(self, tmp_path):
        """Per-tree model: two concurrent worktrees write their OWN logs (each
        ships in its own PR). No shared main-tree funnel. (The append-only logs
        would conflict at EOF if two PRs merge concurrently — an accepted,
        documented tradeoff for the normal sequential-iterate case.)"""
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

        events_a = read_events(wt_a)
        events_b = read_events(wt_b)
        assert len(events_a) == 25
        assert len(events_b) == 25
        assert {e["commit"] for e in events_a} == {f"a-{i:02d}" for i in range(25)}
        assert {e["commit"] for e in events_b} == {f"b-{i:02d}" for i in range(25)}
        # Each worktree's log is independent; the main tree is untouched.
        assert not (main / "shipwright_events.jsonl").exists()

    def test_config_read_events_from_worktree_reads_worktree_log(self, tmp_path):
        """config.read_events (the dashboard's event source) is per-tree."""
        main = _init_main_repo(tmp_path)
        wt = _add_worktree(main, "wt1")
        append_event(wt, {"v": 1, "id": "evt-cfgwt001", "ts": "T",
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
            "--change-type", "tooling", "--none-reason", "test-infra: changed-files capture",
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
# Classification gates (two coexisting layers — decision_log Iterate C.1)
#
# FR-gate (ADR-059 / C.1, iterate-2026-05-21-c1-fr-gate-finalize) is BROADER:
# EVERY iterate work_completed event — incl. BUG and intent-less — must record
# --affected-frs/--new-frs OR --change-type + --none-reason, else exit 1.
# Spec-impact gate (iterate-2026-05-16) is STRICTER but narrower: FEATURE/CHANGE
# only, additionally accepting --spec-impact none + justification. Build events
# (source != iterate) bypass both. The FR-gate runs first.
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
    """record_event.main fails closed on an unclassified iterate work event.

    The FR-gate (C.1) gates ALL iterates; the spec-impact gate adds the
    FEATURE/CHANGE-only --spec-impact-none-needs-justification check. Build
    events bypass both. See the section comment above for the two-gate model.
    """

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

    def test_spec_impact_none_without_change_type_fails_fr_gate(self, project):
        """ADR-059 C.1: --spec-impact none + justification satisfies only the
        stricter (FEATURE/CHANGE) spec-impact gate, NOT the broader FR-gate,
        which runs first across ALL iterates. A no-FR change must classify via
        --change-type/--none-reason (see test_work_completed_change_type)."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "change", "--commit", "g6",
            "--description", "internal refactor",
            "--spec-impact", "none",
            "--spec-impact-justification", "no user-visible behavior change",
        ])
        assert rc == 1
        assert read_events(project) == []

    def test_build_event_without_frs_unaffected(self, project):
        """Build events are NOT gated — only iterate feature/change."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "build", "--commit", "g7", "--section", "01-x",
        ])
        assert rc == 0

    def test_bug_intent_without_classification_fails(self, project):
        """ADR-059 C.1: the FR-gate applies to ALL iterates incl. BUG — a bug
        iterate must still classify via FRs or --change-type/--none-reason."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--intent", "bug", "--commit", "g8",
            "--description", "fix crash",
        ])
        assert rc == 1
        assert read_events(project) == []

    def test_intentless_iterate_without_classification_fails(self, project):
        """ADR-059 C.1: the FR-gate applies to every iterate work_completed
        regardless of --intent — an intentless event must still classify."""
        rc = record_main([
            "--project-root", str(project),
            "--type", "work_completed",
            "--source", "iterate", "--commit", "g9",
            "--description", "legacy-style event",
        ])
        assert rc == 1
        assert read_events(project) == []
