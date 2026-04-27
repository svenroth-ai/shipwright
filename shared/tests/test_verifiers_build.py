"""Tests for shared/scripts/tools/verifiers/build_checks.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from tools.verifiers.build_checks import (
    check_all_sections_complete,
    check_build_test_files_exist,
    check_c5_changelog_has_bullet_per_section,
    check_commit_sha_in_git,
    check_per_section_adr_recorded,
    check_per_section_work_completed_events,
    check_phase_history_build_has_sections,
    run_build_checks,
)
from tools.verifiers.common import Severity


def seed_canon_build(
    root: Path,
    *,
    split: str = "01-auth",
    sections: list[dict] | None = None,
    run_id: str = "build-20260414-test",
    write_canon_artifacts: bool = True,
) -> None:
    """Seed a minimally-valid build project.

    ``sections`` entries default to two complete sections with test
    files, commit shas, and associated work_completed events/ADR
    references/CHANGELOG bullets. Callers selectively tear down
    individual artifacts in failure-path tests.
    """
    sections = sections or [
        {
            "name": "01-model",
            "status": "complete",
            "commit": "abc12340",
            "tests_passed": 5,
            "tests_total": 5,
            "test_file": "tests/01-model.test.ts",
        },
        {
            "name": "02-routes",
            "status": "complete",
            "commit": "abc12341",
            "tests_passed": 3,
            "tests_total": 3,
            "test_files": ["tests/02-routes.test.ts"],
        },
    ]

    (root / "shipwright_build_config.json").write_text(
        json.dumps({
            "current_split": split,
            "sections": sections,
        })
    )

    # Create declared test files
    for sec in sections:
        for key in ("test_file", "test_files"):
            val = sec.get(key)
            if isinstance(val, str):
                (root / val).parent.mkdir(parents=True, exist_ok=True)
                (root / val).write_text("// test\n")
            elif isinstance(val, list):
                for tp in val:
                    (root / tp).parent.mkdir(parents=True, exist_ok=True)
                    (root / tp).write_text("// test\n")

    if not write_canon_artifacts:
        return

    # C1: work_completed event per section
    events_lines = []
    for sec in sections:
        if sec.get("status") != "complete":
            continue
        events_lines.append(json.dumps({
            "type": "work_completed",
            "source": "build",
            "section": sec["name"],
            "commit": sec.get("commit", ""),
            "timestamp": "2026-04-14T10:00:00Z",
        }))
    (root / "shipwright_events.jsonl").write_text("\n".join(events_lines) + "\n")

    # C2: build_dashboard mentions "build"
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Dashboard\n\n## Phases\n\n- build: in progress\n"
    )

    # C3: fresh handoff
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")

    # C4: ADR per section via **Section:** bullet — unique IDs
    adr_body = "# Decision Log\n\n"
    adr_counter = 100
    for sec in sections:
        if sec.get("status") != "complete":
            continue
        adr_body += (
            f"### ADR-{adr_counter}: Build {sec['name']} decision\n"
            f"- **Status:** accepted\n"
            f"- **Section:** {sec['name']}\n\n"
        )
        adr_counter += 1
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(adr_body)

    # C5: CHANGELOG [Unreleased] bullet per section
    bullets = "\n".join(
        f"- Build: {split}/{s['name']} complete ({s.get('tests_passed', 0)}/{s.get('tests_total', 0)} tests)"
        for s in sections if s.get("status") == "complete"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n### Added\n{bullets}\n"
    )

    # phase_history[build] with sections sub-array
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {
            "build": [{
                "run_id": run_id,
                "date": "2026-04-14",
                "split": split,
                "sections": [
                    {"id": s["name"], "status": s.get("status", "")}
                    for s in sections if s.get("status") == "complete"
                ],
            }]
        }
    }))


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def test_all_sections_complete_passes(tmp_path):
    seed_canon_build(tmp_path)
    r = check_all_sections_complete(tmp_path)
    assert r.ok is True


def test_all_sections_complete_fails_on_incomplete(tmp_path):
    seed_canon_build(tmp_path, sections=[
        {"name": "01-a", "status": "complete", "commit": "abc0"},
        {"name": "02-b", "status": "in_progress"},
    ])
    r = check_all_sections_complete(tmp_path)
    assert r.ok is False
    assert "02-b" in r.detail


def test_all_sections_complete_fails_when_empty(tmp_path):
    (tmp_path / "shipwright_build_config.json").write_text(json.dumps({"sections": []}))
    r = check_all_sections_complete(tmp_path)
    assert r.ok is False


# ---------------------------------------------------------------------------
# B3: check_build_test_files_exist
# ---------------------------------------------------------------------------

def test_b3_test_files_exist_happy(tmp_path):
    seed_canon_build(tmp_path)
    r = check_build_test_files_exist(tmp_path)
    assert r.ok is True


def test_b3_test_files_exist_detects_missing(tmp_path):
    seed_canon_build(tmp_path)
    (tmp_path / "tests" / "01-model.test.ts").unlink()
    r = check_build_test_files_exist(tmp_path)
    assert r.ok is False
    assert "01-model.test.ts" in r.detail


def test_b3_test_files_exist_passes_when_no_test_refs(tmp_path):
    seed_canon_build(tmp_path, sections=[
        {"name": "01-refactor", "status": "complete", "commit": "abc0"},
    ])
    r = check_build_test_files_exist(tmp_path)
    assert r.ok is True
    assert "no test files" in r.detail.lower()


# ---------------------------------------------------------------------------
# B6: check_commit_sha_in_git
# ---------------------------------------------------------------------------

def test_b6_commit_sha_in_git_passes_when_git_reports_reachable(tmp_path):
    seed_canon_build(tmp_path)
    # Mock git cat-file to always succeed
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("tools.verifiers.build_checks.subprocess.run", return_value=completed):
        r = check_commit_sha_in_git(tmp_path)
    assert r.ok is True


def test_b6_commit_sha_in_git_fails_when_git_reports_unreachable(tmp_path):
    seed_canon_build(tmp_path)
    # First call succeeds, second fails (partial history rewrite)
    calls = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="bad obj"),
    ]
    with patch("tools.verifiers.build_checks.subprocess.run", side_effect=calls):
        r = check_commit_sha_in_git(tmp_path)
    assert r.ok is False
    assert "not reachable" in r.detail


def test_b6_commit_sha_in_git_skips_when_no_commits(tmp_path):
    seed_canon_build(tmp_path, sections=[
        {"name": "01-a", "status": "complete"},  # no commit field
    ])
    r = check_commit_sha_in_git(tmp_path)
    assert r.ok is True


# ---------------------------------------------------------------------------
# Per-section C1 (work_completed events)
# ---------------------------------------------------------------------------

def test_c1_per_section_passes_when_all_sections_have_events(tmp_path):
    seed_canon_build(tmp_path)
    r = check_per_section_work_completed_events(tmp_path)
    assert r.ok is True


def test_c1_per_section_fails_on_missing_event(tmp_path):
    seed_canon_build(tmp_path)
    # Overwrite events.jsonl with only one section's event
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "work_completed",
            "source": "build",
            "section": "01-model",
        }) + "\n"
    )
    r = check_per_section_work_completed_events(tmp_path)
    assert r.ok is False
    assert "02-routes" in r.detail


def test_c1_per_section_ignores_non_build_source(tmp_path):
    seed_canon_build(tmp_path, sections=[
        {"name": "01-model", "status": "complete", "commit": "abc"},
    ])
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "work_completed",
            "source": "iterate",  # wrong source
            "section": "01-model",
        }) + "\n"
    )
    r = check_per_section_work_completed_events(tmp_path)
    assert r.ok is False


# ---------------------------------------------------------------------------
# Per-section C4 (ADR references)
# ---------------------------------------------------------------------------

def test_c4_per_section_passes_when_every_section_has_adr_reference(tmp_path):
    seed_canon_build(tmp_path)
    r = check_per_section_adr_recorded(tmp_path)
    assert r.ok is True


def test_c4_per_section_fails_on_missing_reference(tmp_path):
    seed_canon_build(tmp_path)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-100: Build 01-model decision\n"
        "- **Status:** accepted\n"
        "- **Section:** 01-model\n"
    )
    r = check_per_section_adr_recorded(tmp_path)
    assert r.ok is False
    assert "02-routes" in r.detail


# ---------------------------------------------------------------------------
# C5: CHANGELOG has bullet per section
# ---------------------------------------------------------------------------

def test_c5_per_section_bullets_passes(tmp_path):
    seed_canon_build(tmp_path)
    r = check_c5_changelog_has_bullet_per_section(tmp_path)
    assert r.ok is True


def test_c5_per_section_bullets_fails_on_missing_section(tmp_path):
    seed_canon_build(tmp_path)
    # CHANGELOG missing the 02-routes bullet
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n"
        "- Build: 01-auth/01-model complete (5/5 tests)\n"
    )
    r = check_c5_changelog_has_bullet_per_section(tmp_path)
    assert r.ok is False
    assert "02-routes" in r.detail


def test_c5_per_section_bullets_warn_when_changelog_missing(tmp_path):
    seed_canon_build(tmp_path)
    (tmp_path / "CHANGELOG.md").unlink()
    r = check_c5_changelog_has_bullet_per_section(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


# ---------------------------------------------------------------------------
# phase_history sections sub-array
# ---------------------------------------------------------------------------

def test_phase_history_build_has_sections_happy(tmp_path):
    seed_canon_build(tmp_path, run_id="build-happy")
    r = check_phase_history_build_has_sections(tmp_path, "build-happy")
    assert r.ok is True


def test_phase_history_build_has_sections_fails_on_missing_section(tmp_path):
    seed_canon_build(tmp_path, run_id="build-r1")
    # Write phase_history that only records one section
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {
            "build": [{
                "run_id": "build-r1",
                "sections": [{"id": "01-model", "status": "complete"}],
            }]
        }
    }))
    r = check_phase_history_build_has_sections(tmp_path, "build-r1")
    assert r.ok is False
    assert "02-routes" in r.detail


def test_phase_history_build_has_sections_skips_blank_run_id(tmp_path):
    seed_canon_build(tmp_path)
    r = check_phase_history_build_has_sections(tmp_path, "")
    assert r.ok is True


# ---------------------------------------------------------------------------
# run_build_checks orchestrator
# ---------------------------------------------------------------------------

def test_run_build_checks_green_on_happy_path(tmp_path):
    seed_canon_build(tmp_path, run_id="build-happy")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("tools.verifiers.build_checks.subprocess.run", return_value=completed):
        results = run_build_checks(tmp_path, run_id="build-happy")

    red = [
        r for r in results
        if not r.is_skipped and not r.ok and r.severity == Severity.ERROR.value
    ]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_build_checks_detects_missing_c1(tmp_path):
    seed_canon_build(tmp_path, run_id="build-happy")
    (tmp_path / "shipwright_events.jsonl").write_text("")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("tools.verifiers.build_checks.subprocess.run", return_value=completed):
        results = run_build_checks(tmp_path, run_id="build-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C1" in r.name for r in red)


def test_run_build_checks_detects_missing_test_files(tmp_path):
    seed_canon_build(tmp_path, run_id="build-happy")
    (tmp_path / "tests" / "01-model.test.ts").unlink()
    (tmp_path / "tests" / "02-routes.test.ts").unlink()
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("tools.verifiers.build_checks.subprocess.run", return_value=completed):
        results = run_build_checks(tmp_path, run_id="build-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("B3" in r.name for r in red)
