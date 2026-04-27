"""Combined tests for iterate 12.4 verifier modules.

Covers:

- ``test_checks.py`` — phase-own ``check_test_results_file_fresh`` +
  canon dispatcher (C4/C5 skipped by policy).
- ``changelog_checks.py`` — Sonder-Checks ``check_git_tag_exists`` and
  ``check_changelog_version_matches_tag`` with ``subprocess.run``
  mocks, plus canon dispatcher.
- ``deploy_checks.py`` — phase-own ``check_test_gate_passed`` (mirrors
  the legacy test gate) plus canon dispatcher.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from tools.verifiers.changelog_checks import (
    _extract_latest_version_from_changelog,
    check_changelog_version_matches_tag,
    check_git_tag_exists,
    run_changelog_checks,
)
from tools.verifiers.common import Severity
from tools.verifiers.deploy_checks import (
    check_test_gate_passed,
    run_deploy_checks,
)
from tools.verifiers.test_checks import (
    check_test_results_file_fresh,
    run_test_checks,
)


def _seed_canon_backplate(root: Path, phase: str, run_id: str) -> None:
    """Seed every canon artifact a phase verifier can assert on.

    Covers C1 (event), C2 (dashboard), C3 (handoff), phase_history
    for the given phase, plus ADR F1/F2/F3 baseline. Phase-own files
    (test_results, CHANGELOG version block, etc.) are added by the
    per-phase seed helpers below.
    """
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "phase_completed",
            "phase": phase,
            "timestamp": "2026-04-14T10:00:00Z",
        }) + "\n"
    )
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        f"# Dashboard\n\n- {phase}: complete\n"
    )
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: Anchor\n- **Status:** accepted\n"
    )
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {phase: [{"run_id": run_id, "date": "2026-04-14"}]},
    }))


# =============================================================================
# test_checks
# =============================================================================

def test_check_test_results_fresh_passes_on_green(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 10, "total": 10},
    }))
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is True


def test_check_test_results_fresh_fails_on_missing(tmp_path):
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False


def test_check_test_results_fresh_fails_on_zero_total(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 0, "total": 0},
    }))
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False


def test_check_test_results_fresh_warns_on_partial_pass(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 3, "total": 5},
    }))
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


def test_run_test_checks_happy_path(tmp_path):
    _seed_canon_backplate(tmp_path, "test", "test-happy")
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 10, "total": 10},
    }))
    results = run_test_checks(tmp_path, run_id="test-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_test_checks_does_not_require_c4_or_c5(tmp_path):
    _seed_canon_backplate(tmp_path, "test", "test-happy")
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 10, "total": 10},
    }))
    results = run_test_checks(tmp_path, run_id="test-happy")
    assert not any("C4" in r.name for r in results)
    assert not any("C5" in r.name for r in results)


# =============================================================================
# changelog_checks — _extract_latest_version_from_changelog
# =============================================================================

def test_extract_latest_version_skips_unreleased(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n### Added\n- new stuff\n\n"
        "## [v1.2.0] - 2026-04-14\n\n### Added\n- older\n\n"
        "## [v1.1.0] - 2026-03-01\n"
    )
    assert _extract_latest_version_from_changelog(tmp_path) == "v1.2.0"


def test_extract_latest_version_adds_v_prefix_when_missing(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.0.0] - 2026-04-01\n"
    )
    assert _extract_latest_version_from_changelog(tmp_path) == "v1.0.0"


def test_extract_latest_version_none_when_only_unreleased(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n"
    )
    assert _extract_latest_version_from_changelog(tmp_path) is None


def test_extract_latest_version_none_when_changelog_missing(tmp_path):
    assert _extract_latest_version_from_changelog(tmp_path) is None


# =============================================================================
# changelog_checks — check_git_tag_exists
# =============================================================================

def test_git_tag_exists_passes_when_git_confirms(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "## [v1.2.0]\n"
    )
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123", stderr="")
    with patch("tools.verifiers.changelog_checks.subprocess.run", return_value=completed):
        r = check_git_tag_exists(tmp_path)
    assert r.ok is True
    assert "v1.2.0" in r.detail


def test_git_tag_exists_fails_when_git_missing(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "## [v1.2.0]\n"
    )
    completed = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="")
    with patch("tools.verifiers.changelog_checks.subprocess.run", return_value=completed):
        r = check_git_tag_exists(tmp_path)
    assert r.ok is False
    assert "v1.2.0" in r.detail


def test_git_tag_exists_warns_when_no_released_version(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("## [Unreleased]\n")
    r = check_git_tag_exists(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


# =============================================================================
# changelog_checks — check_changelog_version_matches_tag
# =============================================================================

def test_changelog_version_matches_tag_happy(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n## [v1.2.0]\n"
    )
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.2.0\nv1.1.0\n", stderr="")
    with patch("tools.verifiers.changelog_checks.subprocess.run", return_value=completed):
        r = check_changelog_version_matches_tag(tmp_path)
    assert r.ok is True


def test_changelog_version_matches_tag_drift(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n## [v1.2.0]\n"
    )
    # Git reports a newer tag than CHANGELOG knows about
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.3.0\nv1.2.0\n", stderr="")
    with patch("tools.verifiers.changelog_checks.subprocess.run", return_value=completed):
        r = check_changelog_version_matches_tag(tmp_path)
    assert r.ok is False
    assert "v1.3.0" in r.detail
    assert "v1.2.0" in r.detail


def test_changelog_version_matches_tag_no_releases(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("## [Unreleased]\n")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("tools.verifiers.changelog_checks.subprocess.run", return_value=completed):
        r = check_changelog_version_matches_tag(tmp_path)
    assert r.ok is True
    assert "no releases yet" in r.detail.lower()


def test_changelog_version_matches_tag_git_has_no_tag(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("## [v1.0.0]\n")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("tools.verifiers.changelog_checks.subprocess.run", return_value=completed):
        r = check_changelog_version_matches_tag(tmp_path)
    assert r.ok is False
    assert "no matching git tag" in r.detail.lower()


def test_run_changelog_checks_happy_path(tmp_path):
    _seed_canon_backplate(tmp_path, "changelog", "changelog-happy")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v1.0.0]\n"
    )
    # Mock git for both Sonder-Checks: first call = git rev-parse,
    # second = git tag --list. Use a side_effect list so each invocation
    # returns the right output.
    tag_exists = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123", stderr="")
    tag_list = subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.0.0\n", stderr="")
    with patch(
        "tools.verifiers.changelog_checks.subprocess.run",
        side_effect=[tag_exists, tag_list],
    ):
        results = run_changelog_checks(tmp_path, run_id="changelog-happy")

    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_changelog_checks_does_not_require_c4_or_c5(tmp_path):
    _seed_canon_backplate(tmp_path, "changelog", "changelog-happy")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [v1.0.0]\n"
    )
    tag_exists = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc", stderr="")
    tag_list = subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.0.0\n", stderr="")
    with patch(
        "tools.verifiers.changelog_checks.subprocess.run",
        side_effect=[tag_exists, tag_list],
    ):
        results = run_changelog_checks(tmp_path, run_id="changelog-happy")

    assert not any("C4" in r.name for r in results)
    assert not any("C5" in r.name for r in results)


# =============================================================================
# deploy_checks
# =============================================================================

def test_test_gate_passed_happy(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 10, "total": 10},
        "smoke": {"status": "pass"},
    }))
    r = check_test_gate_passed(tmp_path)
    assert r.ok is True


def test_test_gate_passed_blocked_on_missing_results(tmp_path):
    r = check_test_gate_passed(tmp_path)
    assert r.ok is False


def test_test_gate_passed_blocked_on_failing_units(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 3, "total": 5},
    }))
    r = check_test_gate_passed(tmp_path)
    assert r.ok is False


def test_test_gate_passed_blocked_on_failed_smoke(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 5, "total": 5},
        "smoke": {"status": "fail"},
    }))
    r = check_test_gate_passed(tmp_path)
    assert r.ok is False
    assert "smoke" in r.detail.lower()


def test_run_deploy_checks_happy_path(tmp_path):
    _seed_canon_backplate(tmp_path, "deploy", "deploy-happy")
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 5, "total": 5},
        "smoke": {"status": "pass"},
    }))
    results = run_deploy_checks(tmp_path, run_id="deploy-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_deploy_checks_does_not_require_c4_or_c5(tmp_path):
    _seed_canon_backplate(tmp_path, "deploy", "deploy-happy")
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 5, "total": 5},
        "smoke": {"status": "pass"},
    }))
    results = run_deploy_checks(tmp_path, run_id="deploy-happy")
    assert not any("C4" in r.name for r in results)
    assert not any("C5" in r.name for r in results)


def test_run_deploy_checks_blocks_on_missing_test_gate(tmp_path):
    _seed_canon_backplate(tmp_path, "deploy", "deploy-happy")
    # No test results → test gate fails
    results = run_deploy_checks(tmp_path, run_id="deploy-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("test gate" in r.name.lower() for r in red)
