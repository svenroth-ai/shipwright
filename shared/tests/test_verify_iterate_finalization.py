"""Tests for the iterate finalization verifier.

The verifier is a deterministic checklist that runs as the last F-step of
any iterate run and confirms all mandatory finalization artifacts were
actually written. Shipwright keeps a lot of cross-artifact sync invariants
(events.jsonl ↔ iterate_history ↔ decision_log ↔ changelog ↔ session_handoff)
and the verifier is the guard that prevents "I forgot that step" regressions.
"""

import json
from pathlib import Path

import pytest


def _agent_docs_root(tmp: Path) -> Path:
    """Return canonical agent_docs subdir under tmp, creating parents."""
    p = tmp / ".shipwright" / "agent_docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


from tools.verify_iterate_finalization import (
    CheckResult,
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
