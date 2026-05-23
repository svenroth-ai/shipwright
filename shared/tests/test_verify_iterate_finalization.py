"""Tests for the iterate finalization verifier.

The verifier is a deterministic checklist that runs as the last F-step of
any iterate run and confirms all mandatory finalization artifacts were
actually written. Shipwright keeps a lot of cross-artifact sync invariants
(events.jsonl ↔ iterate_history ↔ decision_log ↔ changelog ↔ session_handoff)
and the verifier is the guard that prevents "I forgot that step" regressions.
"""

import json
import subprocess
from pathlib import Path

import pytest


# Linked worktrees come from the shared ``make_worktree`` fixture
# (shared/tests/conftest.py).


def _agent_docs_root(tmp: Path) -> Path:
    """Return canonical agent_docs subdir under tmp, creating parents."""
    p = tmp / ".shipwright" / "agent_docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


from tools.verify_iterate_finalization import (
    CheckResult,
    Severity,
    check_adr_in_iterate_history,
    check_changelog_unreleased,
    check_events_has_commit,
    check_iterate_history_has_run_id,
    check_session_handoff_fresh,
    run_all_checks,
)
from tools.verifiers.iterate_checks import (
    check_build_dashboard_has_run_id,
    check_architecture_reviewed,
    check_conventions_reviewed,
    check_spec_impact_recorded,
    check_surface_verification,
)


# ──────────────────────────────────────────────────────────────────────
# Helper: seed a minimally-valid project
# ──────────────────────────────────────────────────────────────────────

def seed_project(root: Path, run_id: str, commit_hash: str, adr: str = "ADR-999") -> None:
    """Create a tmp project state that would pass every check."""
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)

    (root / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": run_id, "adr": adr, "type": "bug"},
        ],
    }))

    (root / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": commit_hash}) + "\n"
    )

    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        f"# Decision Log\n\n### {adr}: Test decision\n- **Date:** 2026-04-13\n"
    )

    (root.parent / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n### Fixed\n- Something ([ADR-999])\n"
    )

    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")

    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        f"# Build Dashboard\nrun_id: {run_id}\n"
    )


# ──────────────────────────────────────────────────────────────────────
# check_iterate_history_has_run_id
# ──────────────────────────────────────────────────────────────────────

def test_iterate_history_passes_when_run_id_present(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "iterate-2026-04-13-foo"}],
    }))
    result = check_iterate_history_has_run_id(proj, "iterate-2026-04-13-foo")
    assert result.ok is True
    assert "iterate_history" in result.name


def test_iterate_history_fails_when_run_id_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "iterate-2026-04-13-other"}],
    }))
    result = check_iterate_history_has_run_id(proj, "iterate-2026-04-13-foo")
    assert result.ok is False


def test_iterate_history_fails_when_file_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_iterate_history_has_run_id(proj, "iterate-foo")
    assert result.ok is False


# ──────────────────────────────────────────────────────────────────────
# check_events_has_commit
# ──────────────────────────────────────────────────────────────────────

def test_events_passes_when_commit_present(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "task_created", "commit": "abcd1234"}) + "\n"
    )
    result = check_events_has_commit(proj, "abcd1234")
    assert result.ok is True


def test_events_fails_when_commit_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "task_created", "commit": "wrong"}) + "\n"
    )
    result = check_events_has_commit(proj, "abcd1234")
    assert result.ok is False


def test_events_fails_when_file_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_events_has_commit(proj, "abcd1234")
    assert result.ok is False


def test_events_check_resolves_main_log_from_worktree(git_origin_repo, make_worktree):
    """check_events_has_commit run from inside an iterate worktree must read
    the MAIN repo's event log — that is where F7 records the commit."""
    work, _ = git_origin_repo
    (work / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": "ma1nc0m"}) + "\n",
        encoding="utf-8",
    )
    wt = make_worktree(work, "probe")
    result = check_events_has_commit(wt, "ma1nc0m")
    assert result.ok is True


def test_boundary_roundtrip_worktree_producer_to_verifier(git_origin_repo, make_worktree):
    """AC-6 boundary round-trip: an event WRITTEN from a worktree via
    record_event is READ BACK by the F11 verifier from that same worktree —
    both resolve the one canonical main-repo log. This pins producer and
    consumer to the same path."""
    from tools.record_event import append_event

    work, _ = git_origin_repo
    wt = make_worktree(work, "probe")
    append_event(wt, {"v": 1, "id": "evt-rt000001", "ts": "T",
                      "type": "work_completed", "source": "iterate",
                      "commit": "r0undtr1p"})
    # Producer wrote the MAIN log, not the throwaway worktree copy...
    assert (work / "shipwright_events.jsonl").exists()
    assert not (wt / "shipwright_events.jsonl").exists()
    # ...and the consumer (verifier) reads it back from the worktree.
    assert check_events_has_commit(wt, "r0undtr1p").ok is True


# ──────────────────────────────────────────────────────────────────────
# check_adr_in_iterate_history
# ──────────────────────────────────────────────────────────────────────

def test_adr_check_passes_when_both_config_and_log_align(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "r1", "adr": "ADR-042"}],
    }))
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "# Decision Log\n\n### ADR-042: Some decision\n- **Date:** 2026-04-13\n"
    )
    result = check_adr_in_iterate_history(proj, "r1")
    assert result.ok is True


def test_adr_check_fails_when_adr_not_in_decision_log(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "r1", "adr": "ADR-042"}],
    }))
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text("# Decision Log\n")
    result = check_adr_in_iterate_history(proj, "r1")
    assert result.ok is False


def test_adr_check_fails_when_iterate_history_has_no_adr_for_run(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "r1"}],
    }))
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text("# Decision Log\n")
    result = check_adr_in_iterate_history(proj, "r1")
    assert result.ok is False


# ----- H decision-drop pattern: run-id ADR identity ------------------

def test_adr_check_passes_with_pending_decision_drop(tmp_path):
    """entry.adr is a run-id; the ADR lives as a decision-drop awaiting
    aggregation at /shipwright-changelog time."""
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": "iterate-20260515-x", "adr": "iterate-20260515-x"},
        ],
    }))
    drops = proj / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "iterate-20260515-x_001.json").write_text("{}")
    result = check_adr_in_iterate_history(proj, "iterate-20260515-x")
    assert result.ok is True
    assert "decision-drop" in result.detail


def test_adr_check_finds_decision_drop_in_main_repo_from_worktree(
    git_origin_repo, make_worktree
):
    """F11 reality: check_adr_in_iterate_history runs with project_root = the
    iterate worktree, but write_decision_drop writes the drop next to the
    MAIN repo. The verifier must resolve the drop dir against the main repo
    too — otherwise a freshly-written ADR is reported missing at F11."""
    from tools.write_decision_drop import write_decision_drop

    work, _ = git_origin_repo
    run_id = "iterate-20260519-wt-adr"
    wt = make_worktree(work, "wt-adr")
    (wt / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    # F5c writes the iterate_history entry into the worktree (project_root).
    (wt / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": [{"run_id": run_id, "adr": run_id}]}),
        encoding="utf-8",
    )
    # F3 writes the decision-drop — worktree-aware, lands next to the MAIN repo.
    write_decision_drop(
        wt, run_id=run_id, section="Iterate — bug: x", title="x",
        context="c", decision="d", consequences="k",
    )
    result = check_adr_in_iterate_history(wt, run_id)
    assert result.ok is True
    assert "decision-drop" in result.detail


def test_adr_check_passes_when_runid_aggregated_into_log(tmp_path):
    """Post-aggregation: the ADR is in decision_log.md with a Run-ID: line
    linking it to the run-id used as entry.adr."""
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": "iterate-20260515-x", "adr": "iterate-20260515-x"},
        ],
    }))
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "# Decision Log\n\n### ADR-050: A decision\n"
        "- **Date:** 2026-05-15\n- **Run-ID:** iterate-20260515-x\n"
    )
    result = check_adr_in_iterate_history(proj, "iterate-20260515-x")
    assert result.ok is True


def test_adr_check_fails_when_runid_has_no_drop_and_not_in_log(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": "iterate-20260515-x", "adr": "iterate-20260515-x"},
        ],
    }))
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text("# Decision Log\n")
    result = check_adr_in_iterate_history(proj, "iterate-20260515-x")
    assert result.ok is False


# ──────────────────────────────────────────────────────────────────────
# check_changelog_unreleased
# ──────────────────────────────────────────────────────────────────────

def test_changelog_passes_when_unreleased_has_bullets(tmp_path):
    # CHANGELOG.md lives at the repo root, one level above the project dir
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- Bug 1\n- Bug 2\n"
    )
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_changelog_unreleased(proj)
    assert result.ok is True


def test_changelog_fails_when_unreleased_is_empty(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v0.1.0]\n- old\n"
    )
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_changelog_unreleased(proj)
    assert result.ok is False


def test_changelog_warns_when_file_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_changelog_unreleased(proj)
    assert result.ok is False


# ----- drop-directory model (post-aggregate_changelog refactor) ------

def test_changelog_passes_with_drop_file_for_run_id(tmp_path):
    """Drop-directory model: CHANGELOG-unreleased.d/<category>/<run_id>_NNN.md
    is the canonical place for entries between releases. The check must
    accept this as valid even when CHANGELOG.md [Unreleased] is empty.
    """
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v0.1.0]\n- old\n"
    )
    drop_dir = tmp_path / "CHANGELOG-unreleased.d" / "Fixed"
    drop_dir.mkdir(parents=True)
    (drop_dir / "iter-foo_001.md").write_text("- something fixed\n")
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_changelog_unreleased(proj, run_id="iter-foo")
    assert result.ok is True


def test_changelog_passes_with_any_drop_file_when_no_run_id(tmp_path):
    """Backward-compat: when run_id is not provided (legacy callers),
    presence of any non-.gitkeep drop file still satisfies the check.
    """
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v0.1.0]\n- old\n"
    )
    drop_dir = tmp_path / "CHANGELOG-unreleased.d" / "Added"
    drop_dir.mkdir(parents=True)
    (drop_dir / "some-iterate_001.md").write_text("- new feature\n")
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_changelog_unreleased(proj)
    assert result.ok is True


def test_changelog_ignores_gitkeep_only_drop_dir(tmp_path):
    """A scaffolded drop-dir with only .gitkeep files must NOT count as
    having entries — that's the empty state shipped by adopt.
    """
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v0.1.0]\n- old\n"
    )
    for cat in ("Added", "Fixed", "Changed"):
        d = tmp_path / "CHANGELOG-unreleased.d" / cat
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("")
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_changelog_unreleased(proj)
    assert result.ok is False


def test_changelog_drop_file_for_other_run_id_does_not_satisfy(tmp_path):
    """When a specific run_id is requested, a drop file from a DIFFERENT
    iterate must not count — otherwise we'd accept the previous iterate's
    entry as proof for the current one.
    """
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v0.1.0]\n- old\n"
    )
    drop_dir = tmp_path / "CHANGELOG-unreleased.d" / "Fixed"
    drop_dir.mkdir(parents=True)
    (drop_dir / "other-iterate_001.md").write_text("- something else\n")
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_changelog_unreleased(proj, run_id="iter-foo")
    assert result.ok is False


# ──────────────────────────────────────────────────────────────────────
# check_session_handoff_fresh
# ──────────────────────────────────────────────────────────────────────

def test_session_handoff_passes_when_file_is_fresh(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh content")
    # max_age default is 600s, the file was just written
    result = check_session_handoff_fresh(proj)
    assert result.ok is True


def test_session_handoff_warns_when_file_is_stale(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    handoff = proj / ".shipwright" / "agent_docs" / "session_handoff.md"
    handoff.write_text("old")
    # Force mtime to 2 hours ago
    import os
    import time
    old_time = time.time() - 7200
    os.utime(handoff, (old_time, old_time))
    result = check_session_handoff_fresh(proj, max_age_seconds=600)
    assert result.ok is False


def test_session_handoff_missing_is_a_warning(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    result = check_session_handoff_fresh(proj)
    assert result.ok is False


# ──────────────────────────────────────────────────────────────────────
# run_all_checks orchestrator
# ──────────────────────────────────────────────────────────────────────

def test_run_all_checks_returns_green_on_happy_path(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    seed_project(proj, "iterate-foo", "abcd1234", adr="ADR-999")
    results = run_all_checks(proj, run_id="iterate-foo", commit_hash="abcd1234")
    assert all(r.ok for r in results), [
        f"{r.name}: {r.detail}" for r in results if not r.ok
    ]


def test_run_all_checks_returns_red_when_run_id_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    seed_project(proj, "iterate-foo", "abcd1234")
    results = run_all_checks(proj, run_id="iterate-MISSING", commit_hash="abcd1234")
    red = [r for r in results if not r.ok]
    assert len(red) >= 1


def test_run_all_checks_returns_red_when_commit_not_in_events(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    seed_project(proj, "iterate-foo", "abcd1234")
    results = run_all_checks(proj, run_id="iterate-foo", commit_hash="WRONG")
    red = [r for r in results if not r.ok]
    assert any("events" in r.name for r in red)


def test_run_all_checks_green_under_drop_directory_model(tmp_path):
    """End-to-end: drop-dir-only project (CHANGELOG.md [Unreleased] empty,
    drop file present, dashboard shows commit hash but no run_id literal)
    must pass run_all_checks. This is the post-aggregate_changelog steady
    state — the bug this iterate fixes.
    """
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)

    # Empty [Unreleased] in CHANGELOG.md (drop-dir takes over)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v0.1.0]\n- prior\n"
    )
    # Drop file naming convention matches write_changelog_drop.py output
    drop_dir = tmp_path / "CHANGELOG-unreleased.d" / "Fixed"
    drop_dir.mkdir(parents=True)
    (drop_dir / "iterate-foo_001.md").write_text("- something fixed\n")

    # Dashboard shows short SHA only, no run_id literal
    (proj / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Project Activity Dashboard\n\n"
        "| Type | Description | Commit |\n"
        "|------|-------------|--------|\n"
        "| bug  | desc        | abcd123 |\n"
    )

    # Other artifacts seeded normally
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "iterate-foo", "adr": "ADR-999", "type": "bug"}],
    }))
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": "abcd1234"}) + "\n"
    )
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-999: Test\n"
    )
    (proj / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")

    results = run_all_checks(proj, run_id="iterate-foo", commit_hash="abcd1234")
    failures = [r for r in results if not r.ok]
    assert not failures, [
        f"{r.name}: {r.detail}" for r in failures
    ]


# ──────────────────────────────────────────────────────────────────────
# C2: check_build_dashboard_has_run_id
# ──────────────────────────────────────────────────────────────────────

def test_dashboard_passes_when_run_id_present(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text("run_id: iter-42\n")
    result = check_build_dashboard_has_run_id(proj, "iter-42")
    assert result.ok is True


def test_dashboard_warns_when_run_id_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text("old content\n")
    result = check_build_dashboard_has_run_id(proj, "iter-42")
    assert result.ok is False
    assert result.severity == "warning"


def test_dashboard_warns_when_file_missing(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    result = check_build_dashboard_has_run_id(proj, "iter-42")
    assert result.ok is False


# ----- commit-hash fallback (dashboard renders short SHAs, not run_id) -----

def test_dashboard_passes_when_short_sha_present_and_run_id_missing(tmp_path):
    """update_build_dashboard.py renders the truncated commit hash (first
    7 chars) into the Recent Changes table, NOT the run_id. The check
    must accept the short SHA as proof the iterate row landed.
    """
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Build Dashboard\n\n| Type | Description | Tests | Commit |\n"
        "|------|-------------|-------|--------|\n"
        "| bug  | something   | 10/10 | abc1234 |\n"
    )
    result = check_build_dashboard_has_run_id(
        proj, "iter-42", commit_hash="abc1234deadbeef0123",
    )
    assert result.ok is True


def test_dashboard_warns_when_neither_run_id_nor_sha_present(tmp_path):
    """Legacy WARN behavior preserved when neither identifier matches."""
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Build Dashboard\n| Commit |\n|--------|\n| f00dbabe |\n"
    )
    result = check_build_dashboard_has_run_id(
        proj, "iter-42", commit_hash="abc1234deadbeef0123",
    )
    assert result.ok is False
    assert result.severity == "warning"


def test_dashboard_run_id_takes_precedence_over_sha_check(tmp_path):
    """When run_id literal is in the dashboard (e.g. embedded as HTML
    comment), pass without needing commit hash. Backward compat for
    dashboards that adopted the run_id-tagged format.
    """
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Build Dashboard\nrun_id: iter-42\n"
    )
    result = check_build_dashboard_has_run_id(proj, "iter-42")
    assert result.ok is True


# ──────────────────────────────────────────────────────────────────────
# Architecture/conventions staleness
# ──────────────────────────────────────────────────────────────────────

def test_architecture_passes_for_bugfix(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "r1", "intent": "bug"}],
    }))
    (proj / ".shipwright" / "agent_docs" / "architecture.md").write_text("old")
    result = check_architecture_reviewed(proj, "r1")
    assert result.ok is True


def test_architecture_warns_for_stale_feature(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    cfg = proj / "shipwright_run_config.json"
    cfg.write_text(json.dumps({
        "iterate_history": [{"run_id": "r1", "intent": "change"}],
    }))
    import time
    arch = proj / ".shipwright" / "agent_docs" / "architecture.md"
    arch.write_text("old arch")
    import os
    os.utime(arch, (time.time() - 3600, time.time() - 3600))
    result = check_architecture_reviewed(proj, "r1")
    assert result.ok is False
    assert result.severity == "warning"


def test_architecture_passes_when_fresh(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    cfg = proj / "shipwright_run_config.json"
    cfg.write_text(json.dumps({
        "iterate_history": [{"run_id": "r1", "intent": "feature"}],
    }))
    import time, os
    os.utime(cfg, (time.time() - 3600, time.time() - 3600))
    (proj / ".shipwright" / "agent_docs" / "architecture.md").write_text("fresh arch")
    result = check_architecture_reviewed(proj, "r1")
    assert result.ok is True


# ──────────────────────────────────────────────────────────────────────
# check_surface_verification (F0.5 audit)
# ──────────────────────────────────────────────────────────────────────


def _seed_iterate_entry(proj: Path, run_id: str, complexity: str) -> None:
    proj.mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": run_id, "complexity": complexity, "type": "feature"},
        ],
    }))


def _write_test_results(proj: Path, block: dict | None) -> None:
    payload: dict = {"iterate_latest": {}}
    if block is not None:
        payload["iterate_latest"]["surface_verification"] = block
    (proj / "shipwright_test_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def test_surface_verification_skipped_for_trivial(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "trivial")
    _write_test_results(proj, None)  # block intentionally absent
    result = check_surface_verification(proj, "r1")
    assert result.is_skipped
    assert "trivial" in result.detail


def test_surface_verification_skipped_for_small(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "small")
    result = check_surface_verification(proj, "r1")
    assert result.is_skipped


def test_surface_verification_fails_when_results_missing_at_medium(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    result = check_surface_verification(proj, "r1")
    assert result.ok is False
    assert "shipwright_test_results.json" in result.detail


def test_surface_verification_fails_when_block_missing_at_medium(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, None)
    result = check_surface_verification(proj, "r1")
    assert result.ok is False
    assert "missing" in result.detail.lower()


def test_surface_verification_fails_for_unknown_surface(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "wat", "runner": "x", "exit_code": 0,
        "tests_run": 1, "evidence_path": "x", "timestamp": "now",
    })
    result = check_surface_verification(proj, "r1")
    assert result.ok is False
    assert "not one of" in result.detail


def test_surface_verification_passes_for_none_with_justification(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "none",
        "runner": "",
        "exit_code": 0,
        "tests_run": 0,
        "evidence_path": "",
        "timestamp": "now",
        "justification": "pure type-hint rename; no runtime path exercised",
    })
    result = check_surface_verification(proj, "r1")
    assert result.ok is True
    assert "justification" in result.detail


def test_surface_verification_fails_for_none_without_justification(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "none", "runner": "", "exit_code": 0,
        "tests_run": 0, "evidence_path": "", "timestamp": "now",
    })
    result = check_surface_verification(proj, "r1")
    assert result.ok is False
    assert "justification" in result.detail


def test_surface_verification_fails_for_blank_justification(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "none", "runner": "", "exit_code": 0,
        "tests_run": 0, "evidence_path": "", "timestamp": "now",
        "justification": "   ",
    })
    result = check_surface_verification(proj, "r1")
    assert result.ok is False


def test_surface_verification_fails_when_tests_run_zero(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "cli", "runner": "pytest -q", "exit_code": 0,
        "tests_run": 0, "evidence_path": "log.txt", "timestamp": "now",
    })
    result = check_surface_verification(proj, "r1")
    assert result.ok is False
    assert "tests_run" in result.detail


def test_surface_verification_fails_when_runner_failed(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "web", "runner": "playwright test", "exit_code": 1,
        "tests_run": 5, "evidence_path": "report.html", "timestamp": "now",
    })
    result = check_surface_verification(proj, "r1")
    assert result.ok is False
    assert "exit_code" in result.detail


def test_surface_verification_passes_for_happy_path(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "cli", "runner": "pytest -q", "exit_code": 0,
        "tests_run": 5, "evidence_path": "log.txt", "timestamp": "now",
    })
    result = check_surface_verification(proj, "r1")
    assert result.ok is True
    assert "tests_run=5" in result.detail
    assert "exit_code=0" in result.detail


def test_surface_verification_fails_when_test_results_malformed(tmp_path):
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    (proj / "shipwright_test_results.json").write_text("{not valid json", encoding="utf-8")
    result = check_surface_verification(proj, "r1")
    assert result.ok is False
    assert "malformed" in result.detail.lower()


def test_surface_verification_run_all_checks_includes_f05(tmp_path):
    """Drift guard — run_all_checks must list the F0.5 audit so a future
    refactor can't silently drop it."""
    proj = tmp_path / "webui"
    _seed_iterate_entry(proj, "r1", "medium")
    _write_test_results(proj, {
        "surface": "cli", "runner": "pytest", "exit_code": 0,
        "tests_run": 1, "evidence_path": "x", "timestamp": "now",
    })
    results = run_all_checks(proj, "r1")
    names = [r.name for r in results]
    assert any("F0.5 surface_verification" in n for n in names), (
        f"F0.5 check missing from run_all_checks; got: {names}"
    )


# ──────────────────────────────────────────────────────────────────────
# check_spec_impact_recorded — spec-impact gate
# (iterate-2026-05-16-spec-impact-gate)
# ──────────────────────────────────────────────────────────────────────

def _seed_entry_with_intent(proj: Path, run_id: str, intent: str) -> None:
    """Seed an iterate_history entry with a chosen intent/type."""
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": run_id, "complexity": "medium", "type": intent},
        ],
    }))


def _write_work_event(proj: Path, commit: str, **fields) -> None:
    """Write a single work_completed event referencing `commit`."""
    evt = {"type": "work_completed", "source": "iterate", "commit": commit}
    evt.update(fields)
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps(evt) + "\n", encoding="utf-8"
    )


def _git_commit(repo: Path, files: dict[str, str], message: str) -> str:
    """Init a git repo (if needed), write `files`, commit, return the SHA."""
    repo.mkdir(parents=True, exist_ok=True)

    def _g(*a: str) -> None:
        subprocess.run(["git", "-C", str(repo), *a],
                       check=True, capture_output=True, text=True)

    if not (repo / ".git").exists():
        _g("init", "-b", "main")
    for rel, content in files.items():
        fp = repo / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    _g("add", "-A")
    _g("-c", "user.name=T", "-c", "user.email=t@t.invalid",
       "commit", "-m", message)
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


def test_spec_impact_skipped_when_run_id_missing(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    result = check_spec_impact_recorded(proj, "absent", "abc1234")
    assert result.ok is True
    assert result.severity == Severity.SKIPPED.value


def test_spec_impact_skipped_for_bug_intent(tmp_path):
    """A BUG iterate need not touch the spec — the gate skips it."""
    proj = tmp_path / "p"
    _seed_entry_with_intent(proj, "r1", "bug")
    result = check_spec_impact_recorded(proj, "r1", "abc1234")
    assert result.ok is True
    assert result.severity == Severity.SKIPPED.value


def test_spec_impact_none_with_justification_passes(tmp_path):
    proj = tmp_path / "p"
    _seed_entry_with_intent(proj, "r1", "feature")
    _write_work_event(proj, "abc1234", intent="feature",
                      spec_impact="none",
                      spec_impact_justification="behavior-preserving refactor")
    result = check_spec_impact_recorded(proj, "r1", "abc1234")
    assert result.ok is True


def test_spec_impact_none_without_justification_fails(tmp_path):
    proj = tmp_path / "p"
    _seed_entry_with_intent(proj, "r1", "change")
    _write_work_event(proj, "abc1234", intent="change", spec_impact="none")
    result = check_spec_impact_recorded(proj, "r1", "abc1234")
    assert result.ok is False
    assert result.severity == Severity.ERROR.value


def test_spec_impact_passes_when_commit_touches_spec(tmp_path):
    proj = tmp_path / "p"
    commit = _git_commit(proj, {
        ".shipwright/planning/01-x/spec.md": "| FR-01.01 | x | Must |\n",
        "src/app.py": "x = 1\n",
    }, "feat: add FR")
    _seed_entry_with_intent(proj, "r1", "feature")
    _write_work_event(proj, commit, intent="feature", spec_impact="modify")
    result = check_spec_impact_recorded(proj, "r1", commit)
    assert result.ok is True


def test_spec_impact_fails_when_commit_misses_spec(tmp_path):
    """spec_impact=modify recorded, but the commit touched no planning spec."""
    proj = tmp_path / "p"
    commit = _git_commit(proj, {"src/app.py": "x = 1\n"}, "feat: code only")
    _seed_entry_with_intent(proj, "r1", "feature")
    _write_work_event(proj, commit, intent="feature", spec_impact="modify")
    result = check_spec_impact_recorded(proj, "r1", commit)
    assert result.ok is False
    assert result.severity == Severity.ERROR.value


def test_spec_impact_legacy_event_passes_via_commit_diff(tmp_path):
    """A legacy event with no spec_impact still passes if the commit
    actually touched a planning spec.md (fallthrough path)."""
    proj = tmp_path / "p"
    commit = _git_commit(
        proj, {".shipwright/planning/01-x/spec.md": "x\n"}, "spec change"
    )
    _seed_entry_with_intent(proj, "r1", "feature")
    _write_work_event(proj, commit, intent="feature")  # no spec_impact
    result = check_spec_impact_recorded(proj, "r1", commit)
    assert result.ok is True


def test_spec_impact_skipped_when_git_unavailable(tmp_path):
    """Non-git dir + no spec_impact=none → SKIPPED (cannot inspect commit)."""
    proj = tmp_path / "p"
    _seed_entry_with_intent(proj, "r1", "feature")
    _write_work_event(proj, "abc1234", intent="feature")
    result = check_spec_impact_recorded(proj, "r1", "abc1234")
    assert result.ok is True
    assert result.severity == Severity.SKIPPED.value


def test_spec_impact_in_run_all_checks(tmp_path):
    """Drift guard — run_all_checks must list the spec-impact gate so a
    future refactor can't silently drop it."""
    proj = tmp_path / "p"
    _seed_entry_with_intent(proj, "r1", "feature")
    results = run_all_checks(proj, "r1", commit_hash="abc1234")
    names = [r.name for r in results]
    assert any("spec impact" in n.lower() for n in names), (
        f"spec-impact check missing from run_all_checks; got: {names}"
    )


# ──────────────────────────────────────────────────────────────────────
# Multi-commit-iterate-aware checks (iterate-2026-05-23-verifier-multi-commit-aware)
# ──────────────────────────────────────────────────────────────────────

def test_events_check_finds_event_by_run_id_when_head_differs(tmp_path):
    """Multi-commit iterate scenario: F7 recorded the event with the F6
    commit (e.g. abc1234), but a follow-up commit (def5678) advanced HEAD.
    The verifier passes HEAD as commit_hash + run_id. The run_id lookup
    finds the event with the F6 commit and reports it — no false fail."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "work_completed",
            "source": "iterate",
            "commit": "abc1234",
            "adr_id": "iterate-2026-05-23-foo",
        }) + "\n",
        encoding="utf-8",
    )
    result = check_events_has_commit(proj, "def5678", run_id="iterate-2026-05-23-foo")
    assert result.ok is True
    assert "abc1234" in result.detail
    assert "iterate-2026-05-23-foo" in result.detail


def test_events_check_falls_back_to_commit_when_run_id_event_absent(tmp_path):
    """Legacy / non-iterate events that lack adr_id: fallback to commit
    substring search keeps working."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": "abc1234"}) + "\n",
        encoding="utf-8",
    )
    # run_id supplied but no event matches it — falls back to commit search.
    result = check_events_has_commit(proj, "abc1234", run_id="iterate-not-recorded")
    assert result.ok is True


def test_events_check_fails_with_helpful_detail_when_both_paths_miss(tmp_path):
    """Neither the commit nor a run_id-tagged event are present — the
    failure detail names both unresolved identifiers for fast diagnosis."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": "wrong"}) + "\n",
        encoding="utf-8",
    )
    result = check_events_has_commit(proj, "abc1234", run_id="iterate-foo")
    assert result.ok is False
    assert "abc1234" in result.detail
    assert "iterate-foo" in result.detail


def test_events_check_passes_when_event_has_no_commit_field(tmp_path):
    """Pathological — event present for run_id but missing the commit
    field. F7 did run; treat as pass + flag in detail."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "adr_id": "iterate-foo"}) + "\n",
        encoding="utf-8",
    )
    result = check_events_has_commit(proj, "", run_id="iterate-foo")
    assert result.ok is True
    assert "no commit field" in result.detail


def test_spec_impact_resolves_event_by_run_id_in_multi_commit_iterate(tmp_path):
    """Multi-commit iterate: F6 commit touched .shipwright/planning/.../spec.md,
    F7 recorded the event for the F6 commit, then a follow-up F6.5 fix
    commit advanced HEAD without touching the spec. The verifier (passing
    HEAD as commit_hash + the run_id) should find the F7 event by run_id
    and run the spec.md check against the F7 commit — not HEAD."""
    proj = tmp_path / "p"
    # F6 commit touches a spec.md (the iterate's real authored content).
    f6_commit = _git_commit(proj, {
        ".shipwright/planning/01-x/spec.md": "| FR-01.01 | x | Must |\n",
        "src/app.py": "x = 1\n",
    }, "feat: add FR")
    # F6.5 follow-up commit advances HEAD without touching the spec.
    head_commit = _git_commit(proj, {"src/app.py": "x = 2\n"}, "fix: tweak")
    assert f6_commit != head_commit

    _seed_entry_with_intent(proj, "iterate-2026-05-23-foo", "feature")
    # F7 recorded the event against the F6 commit (not HEAD).
    _write_work_event(
        proj, f6_commit, intent="feature", spec_impact="modify",
        adr_id="iterate-2026-05-23-foo",
    )

    # Verifier passes HEAD as commit_hash — but lookup is by run_id.
    result = check_spec_impact_recorded(
        proj, "iterate-2026-05-23-foo", head_commit,
    )
    assert result.ok is True
    assert "1 planning spec.md" in result.detail


def test_spec_impact_falls_back_to_commit_when_run_id_event_absent(tmp_path):
    """When no run_id-tagged event exists, the legacy by-commit lookup
    still works — pinned for back-compat."""
    proj = tmp_path / "p"
    commit = _git_commit(proj, {
        ".shipwright/planning/01-x/spec.md": "spec\n",
    }, "spec change")
    _seed_entry_with_intent(proj, "r1", "feature")
    # Event has no adr_id — the legacy shape.
    _write_work_event(proj, commit, intent="feature", spec_impact="modify")
    result = check_spec_impact_recorded(proj, "r1", commit)
    assert result.ok is True


def test_spec_impact_multi_commit_with_spec_impact_none_still_passes(tmp_path):
    """A multi-commit iterate that recorded spec_impact=none with a
    justification still passes via the run_id lookup, regardless of which
    commit HEAD points at."""
    proj = tmp_path / "p"
    f6 = _git_commit(proj, {"src/app.py": "x = 1\n"}, "feat: no-spec")
    head = _git_commit(proj, {"src/app.py": "x = 2\n"}, "fix: tweak")
    _seed_entry_with_intent(proj, "iterate-r1", "change")
    _write_work_event(
        proj, f6, intent="change", spec_impact="none",
        spec_impact_justification="behavior-preserving refactor",
        adr_id="iterate-r1",
    )
    result = check_spec_impact_recorded(proj, "iterate-r1", head)
    assert result.ok is True
    assert "spec_impact=none" in result.detail


def test_find_work_event_by_run_id_returns_last_when_multiple_match(tmp_path):
    """Pathological case — two events share the same adr_id (e.g. F7
    re-recorded). The lookup returns the chronologically later one, since
    JSONL is append-ordered and the live record is the most recent."""
    from tools.verifiers.iterate_checks import _find_work_event_by_run_id

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": "first", "adr_id": "r1"}) + "\n"
        + json.dumps({"type": "work_completed", "commit": "second", "adr_id": "r1"}) + "\n",
        encoding="utf-8",
    )
    evt = _find_work_event_by_run_id(proj, "r1")
    assert evt is not None
    assert evt["commit"] == "second"


def test_find_work_event_by_run_id_returns_none_for_unknown_run_id(tmp_path):
    """Empty / unknown run_id returns None cleanly — callers can fall
    back to other resolution strategies."""
    from tools.verifiers.iterate_checks import _find_work_event_by_run_id

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": "x", "adr_id": "other"}) + "\n",
        encoding="utf-8",
    )
    assert _find_work_event_by_run_id(proj, "missing") is None
    assert _find_work_event_by_run_id(proj, "") is None


def test_run_all_checks_passes_run_id_to_events_check(tmp_path):
    """Drift guard for the run_id wiring in run_all_checks: a multi-commit
    iterate where commit_hash != event's commit must pass when the F7 event
    is tagged with the run_id."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "iterate-r1", "complexity": "small", "type": "change"}],
    }))
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "work_completed",
            "commit": "f6abc123",
            "adr_id": "iterate-r1",
        }) + "\n",
        encoding="utf-8",
    )
    # Pass a DIFFERENT commit as HEAD — only the run_id lookup can succeed.
    results = run_all_checks(proj, "iterate-r1", commit_hash="head9999")
    events_check = next(r for r in results if "events.jsonl has commit" in r.name)
    assert events_check.ok is True
    assert "f6abc123" in events_check.detail
