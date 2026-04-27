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
