"""Tests for shared/scripts/tools/verifiers/project_checks.py + common helpers.

Exercises the iterate 12.1 project-phase canon dispatcher plus the
``check_phase_history_has_run`` common helper (added in 12.1 for use by
every phase-specific verifier module going forward).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.verifiers.common import (
    Severity,
    check_phase_history_has_run,
)
from tools.verifiers.project_checks import (
    check_manifest_splits_match_dirs,
    check_project_config_status_complete,
    run_project_checks,
)


def seed_canon_project(
    root: Path,
    *,
    splits: list[str] | None = None,
    run_id: str = "project-20260414-test",
    write_canon_artifacts: bool = True,
) -> None:
    """Produce a minimally-valid project that passes every check in
    ``run_project_checks`` when ``write_canon_artifacts=True``.

    Callers selectively tear down individual artifacts in failure-path
    tests so we don't pay the seed cost every time.
    """
    splits = splits or ["01-auth", "02-dashboard"]

    # Project config — status=complete, splits populated
    (root / "shipwright_project_config.json").write_text(
        json.dumps({
            "status": "complete",
            "splits": [{"name": s, "status": "complete"} for s in splits],
        }),
        encoding="utf-8",
    )

    # Planning dirs matching splits
    for s in splits:
        (root / ".shipwright" / "planning" / s).mkdir(parents=True)
        (root / ".shipwright" / "planning" / s / "spec.md").write_text("# spec\n")

    if not write_canon_artifacts:
        return

    # C1 — phase_completed event
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "phase_completed",
            "phase": "project",
            "timestamp": "2026-04-14T10:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )

    # C2 — build_dashboard mentions project
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "## Phases\n\n- project: complete\n"
    )

    # C3 — fresh session_handoff
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")

    # C4 — ADR referencing project
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-027: Project decomposition decision\n"
        "- **Status:** accepted\n"
    )

    # C5 — CHANGELOG [Unreleased] Added bullet (root CHANGELOG)
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n"
        "- Project initialized: demo (2 splits)\n"
    )

    # phase_history — seed via run_config
    (root / "shipwright_run_config.json").write_text(
        json.dumps({
            "phase_history": {
                "project": [{"run_id": run_id, "date": "2026-04-14"}]
            },
        }),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def test_project_config_status_complete_passes(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"})
    )
    r = check_project_config_status_complete(tmp_path)
    assert r.ok is True


def test_project_config_status_in_progress_fails(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "in_progress"})
    )
    r = check_project_config_status_complete(tmp_path)
    assert r.ok is False


def test_project_config_missing_fails(tmp_path):
    r = check_project_config_status_complete(tmp_path)
    assert r.ok is False


def test_manifest_splits_match_dirs_passes_when_aligned(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}, {"name": "02-dashboard"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "02-dashboard").mkdir()
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is True


def test_manifest_splits_match_dirs_warns_on_missing_dir(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}, {"name": "02-dashboard"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    assert "02-dashboard" in r.detail


def test_manifest_splits_match_dirs_warns_on_extra_dir(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "99-rogue").mkdir()
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is False
    assert "99-rogue" in r.detail


def test_manifest_splits_match_dirs_ignores_iterate_subdir(tmp_path):
    """.shipwright/planning/iterate/ is where iterate specs live and should not
    count as an 'extra' split."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir()
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is True


# ---------------------------------------------------------------------------
# check_phase_history_has_run (common helper)
# ---------------------------------------------------------------------------

def test_phase_history_check_passes_when_run_id_present(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {
            "project": [{"run_id": "project-x", "date": "2026-04-14"}],
        },
    }))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is True


def test_phase_history_check_fails_when_run_id_missing(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"project": [{"run_id": "other"}]},
    }))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is False


def test_phase_history_check_fails_when_bucket_missing(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {},
    }))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is False


def test_phase_history_check_fails_when_phase_history_field_missing(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is False


def test_phase_history_check_skips_when_run_id_blank(tmp_path):
    """Callers that don't pass --run-id get a neutral pass — the check
    is about matching a specific id, not about the bucket existing."""
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    r = check_phase_history_has_run(tmp_path, "project", "")
    assert r.ok is True
    assert "skipped" in r.detail.lower()


# ---------------------------------------------------------------------------
# run_project_checks — orchestrator
# ---------------------------------------------------------------------------

def test_run_project_checks_returns_green_on_happy_path(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    results = run_project_checks(tmp_path, run_id="project-happy")

    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_project_checks_detects_missing_c1_event(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Remove the events.jsonl
    (tmp_path / "shipwright_events.jsonl").unlink()
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C1" in r.name for r in red)


def test_run_project_checks_detects_missing_c5_changelog_entry(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Replace CHANGELOG with empty Added section
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- bug\n"
    )
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C5" in r.name for r in red)


def test_run_project_checks_detects_missing_phase_history(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Wipe phase_history
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and "phase_history" in r.name]
    assert len(red) == 1


def test_run_project_checks_with_empty_run_id_skips_phase_history(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Empty phase_history but caller doesn't pass run_id — check is neutral
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    results = run_project_checks(tmp_path, run_id="")
    phase_history_results = [r for r in results if "phase_history" in r.name]
    assert len(phase_history_results) == 1
    assert phase_history_results[0].ok is True  # skipped → neutral pass
