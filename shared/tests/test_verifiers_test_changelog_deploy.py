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
import re
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
    check_failed_liveness_recorded_as_failed,
    check_manual_rollback_proves_alive,
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


def test_test_gate_passed_blocked_on_syntactically_malformed_json(tmp_path):
    """``_load_json_object``'s JSONDecodeError branch, distinct from the
    valid-but-wrong-shape case covered elsewhere — the file exists and is
    unreadable AS JSON, not merely the wrong Python type once parsed."""
    (tmp_path / "shipwright_test_results.json").write_text("{not valid json")
    r = check_test_gate_passed(tmp_path)
    assert r.ok is False
    assert "malformed test results" in r.detail


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


def test_check_test_gate_passed_does_not_crash_on_a_non_object_json_root(tmp_path):
    """External code review (e4-checks-deploy-changelog): valid JSON that
    isn't an object (``[]``, a bare string, a number) used to crash
    ``.get()`` with ``AttributeError`` instead of returning a
    ``CheckResult``.
    """
    (tmp_path / "shipwright_test_results.json").write_text("[1, 2, 3]")
    r = check_test_gate_passed(tmp_path)
    assert r.ok is False
    assert "expected an object" in r.detail


def test_check_test_gate_passed_reads_the_iterate_latest_nested_shape(tmp_path):
    """Self-review round-trip probe against THIS repo's real
    shipwright_test_results.json (e4-checks-deploy-changelog): the
    /shipwright-iterate F5 step nests unit/smoke under an ``iterate_latest``
    wrapper, a different shape than the full-pipeline /shipwright-test
    phase's top-level keys. Reading only the top level made this gate
    always block in every iterate-run repo — an integration test against
    the real file caught it.
    """
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "iterate_latest": {
            "unit": {"passed": 10, "total": 10},
            "smoke": {"status": "pass"},
        },
    }))
    r = check_test_gate_passed(tmp_path)
    assert r.ok is True


def test_check_test_gate_passed_does_not_block_a_green_run_with_skips(tmp_path):
    """Code review (e4-checks-deploy-changelog): ``passed < total`` alone
    counts SKIPPED tests as failures. Seeded from THIS repo's own real
    ``iterate_latest.unit`` shape (``status: "passed"``, ``passed < total``,
    no ``skipped`` key) — the balanced ``passed: 10, total: 10`` fixture
    above cannot see this bug. The layer's own ``status`` verdict must be
    authoritative over the bare count gap.
    """
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "iterate_latest": {
            "unit": {"status": "passed", "passed": 19191, "total": 19260},
            "smoke": {"status": "pass"},
        },
    }))
    r = check_test_gate_passed(tmp_path)
    assert r.ok is True, r.detail


def test_check_test_gate_passed_blocks_on_status_failed_even_if_counts_look_close(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"status": "failed", "passed": 9, "total": 10},
    }))
    r = check_test_gate_passed(tmp_path)
    assert r.ok is False


def test_check_test_gate_passed_falls_back_to_genuine_failure_count_without_status(tmp_path):
    """No ``status`` key at all: falls back to explicit ``skipped``
    accounting rather than the raw gap."""
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 8, "total": 10, "skipped": 2},
    }))
    r = check_test_gate_passed(tmp_path)
    assert r.ok is True, r.detail


# --------------------------------------------------------------------------
# Ledger FR-01.08 #4 — a failed liveness check is recorded as a failed deploy
# --------------------------------------------------------------------------

def _write_smoke_result(root: Path, *, success: bool, checked_at: str = "2026-09-15T10:00:00+00:00") -> None:
    (root / ".shipwright" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "deploy" / "smoke-test-result.json").write_text(json.dumps({
        "success": success, "url": "https://example.invalid", "checked_at": checked_at,
    }))


def test_failed_liveness_check_passes_when_no_smoke_result_recorded(tmp_path):
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is True


def test_failed_liveness_check_passes_when_latest_was_a_success(tmp_path):
    _write_smoke_result(tmp_path, success=True)
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is True


def test_failed_liveness_check_fails_when_no_phase_history_entry_at_all(tmp_path):
    _write_smoke_result(tmp_path, success=False)
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is False
    assert "never recorded" in r.detail


def test_failed_liveness_check_fails_closed_on_a_malformed_latest_entry(tmp_path):
    """Tier-3 PR review, e4-checks-deploy-changelog round 3: a non-dict
    ``phase_history[deploy]`` element (``[null]``, ``["bad"]``) used to crash
    this check with AttributeError on ``latest.get(...)`` instead of failing
    it closed with a well-defined ``CheckResult``."""
    _write_smoke_result(tmp_path, success=False, checked_at="2026-09-15T10:00:00+00:00")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"deploy": [None]},
    }))
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is False
    assert "malformed" in r.detail


def test_failed_liveness_check_fails_when_phase_history_still_says_success(tmp_path):
    _write_smoke_result(tmp_path, success=False, checked_at="2026-09-15T10:00:00+00:00")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"deploy": [
            {"run_id": "r1", "at": "2026-09-15T10:05:00+00:00", "outcome": "success"},
        ]},
    }))
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is False
    assert "'success'" in r.detail


def test_failed_liveness_check_passes_when_phase_history_says_failed(tmp_path):
    _write_smoke_result(tmp_path, success=False, checked_at="2026-09-15T10:00:00+00:00")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"deploy": [
            {"run_id": "r1", "at": "2026-09-15T10:05:00+00:00", "outcome": "failed"},
        ]},
    }))
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is True


def test_failed_liveness_check_fails_closed_when_the_entry_has_no_timestamp_at_all(tmp_path):
    """External code review (e4-checks-deploy-changelog): the original
    staleness check silently SKIPPED itself (fail-open) whenever
    phase_history's ``at`` was missing, falling straight through to the
    outcome check — so an untimestamped legacy ``outcome: "failed"`` entry
    from any point in the project's history could satisfy today's failure.
    A phase_history entry with no parseable timestamp can no longer be
    confirmed as the record of THIS failure and must fail, not pass.
    """
    _write_smoke_result(tmp_path, success=False, checked_at="2026-09-15T10:00:00+00:00")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"deploy": [{"run_id": "r1", "outcome": "failed"}]},
    }))
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is False
    assert "no parseable" in r.detail


def test_failed_liveness_check_fails_closed_when_the_smoke_result_has_no_checked_at(tmp_path):
    """External code review round 2 (e4-checks-deploy-changelog): the
    mirror-image case of the test above — a ``success: false`` smoke
    result with no parseable ``checked_at`` used to skip staleness
    checking entirely too, letting an arbitrarily old ``outcome: "failed"``
    phase_history entry satisfy it.
    """
    (tmp_path / ".shipwright" / "deploy").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "deploy" / "smoke-test-result.json").write_text(
        json.dumps({"success": False, "url": "https://example.invalid"})
    )
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"deploy": [
            {"run_id": "r0", "at": "2020-01-01T00:00:00+00:00", "outcome": "failed"},
        ]},
    }))
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is False
    assert "no parseable checked_at" in r.detail


def test_failed_liveness_check_fails_on_a_stale_phase_history_entry(tmp_path):
    """External review (round 1): a phase_history[deploy] entry that
    PREDATES the failed smoke check cannot be the record of that failure —
    even if it happens to say ``outcome: failed`` for an unrelated, earlier
    reason. Reconciling by time, not just by "latest of each", prevents an
    older phase_history entry from silently satisfying a newer failure.
    """
    _write_smoke_result(tmp_path, success=False, checked_at="2026-09-15T10:00:00+00:00")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"deploy": [
            {"run_id": "r0", "at": "2026-09-15T09:00:00+00:00", "outcome": "failed"},
        ]},
    }))
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is False
    assert "predates" in r.detail


def test_failed_liveness_check_passes_when_a_fresh_entry_confirms_it(tmp_path):
    _write_smoke_result(tmp_path, success=False, checked_at="2026-09-15T10:00:00+00:00")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"deploy": [
            {"run_id": "r1", "at": "2026-09-15T10:05:00+00:00", "outcome": "failed"},
        ]},
    }))
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is True


def test_failed_liveness_check_does_not_crash_on_a_non_object_smoke_result(tmp_path):
    (tmp_path / ".shipwright" / "deploy").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "deploy" / "smoke-test-result.json").write_text('"just a string"')
    r = check_failed_liveness_recorded_as_failed(tmp_path)
    assert r.ok is False
    assert "expected an object" in r.detail


# --------------------------------------------------------------------------
# Ledger FR-01.08 #8 (proves-alive half) — manual rollback → liveness check
# --------------------------------------------------------------------------

def _write_rollback_entry(root: Path, *, invocation: str, recorded_at: str, mutated: bool = True) -> None:
    (root / ".shipwright" / "deploy").mkdir(parents=True, exist_ok=True)
    with (root / ".shipwright" / "deploy" / "rollback-history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "invocation": invocation, "recorded_at": recorded_at,
            "success": True, "mutated": mutated,
        }) + "\n")


def test_manual_rollback_check_passes_when_no_rollback_recorded(tmp_path):
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is True


def test_manual_rollback_check_passes_when_latest_rollback_was_automatic(tmp_path):
    _write_rollback_entry(tmp_path, invocation="auto", recorded_at="2026-09-15T09:00:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is True


def test_manual_rollback_check_fails_when_no_liveness_check_followed(tmp_path):
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "no liveness check has been recorded" in r.detail


def test_manual_rollback_check_fails_when_liveness_check_predates_the_rollback(tmp_path):
    _write_smoke_result(tmp_path, success=True, checked_at="2026-09-15T08:00:00+00:00")
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "predates" in r.detail


def test_manual_rollback_check_passes_when_liveness_check_follows(tmp_path):
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")
    _write_smoke_result(tmp_path, success=True, checked_at="2026-09-15T09:05:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is True


def test_manual_rollback_check_finds_an_earlier_manual_entry_behind_a_later_auto_one(tmp_path):
    """External code review (e4-checks-deploy-changelog): a manual rollback
    followed later by an UNRELATED automatic rollback must not let the
    automatic entry's presence excuse the never-verified manual one — the
    check must reconcile against the last MANUAL entry, not the overall
    last entry of any kind.
    """
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")
    _write_rollback_entry(tmp_path, invocation="auto", recorded_at="2026-09-15T10:00:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "no liveness check has been recorded" in r.detail


def test_manual_rollback_check_does_not_crash_on_a_non_object_smoke_result(tmp_path):
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")
    (tmp_path / ".shipwright" / "deploy" / "smoke-test-result.json").write_text("42")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "expected an object" in r.detail


def test_manual_rollback_check_fails_when_the_follow_up_check_still_found_it_down(tmp_path):
    """The criterion's own word is "proves" the app is alive, not merely
    that a check ran — a fresh liveness check that still reports
    ``success: false`` must not satisfy this row (self-review catch,
    e4-checks-deploy-changelog: the first version of this check only
    looked at timestamps, never at the outcome).
    """
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")
    _write_smoke_result(tmp_path, success=False, checked_at="2026-09-15T09:05:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "did not prove the app alive" in r.detail


def test_manual_rollback_check_fails_closed_on_an_unparseable_smoke_timestamp(tmp_path):
    """Fail-closed on the SMOKE side too, not just the rollback side (round-2
    external code review mirror-image bug, applied here to the proves-alive
    check as well): a ``checked_at`` that does not parse must never be
    silently treated as "no evidence either way, so pass"."""
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")
    _write_smoke_result(tmp_path, success=True, checked_at="not-a-timestamp")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "missing a parseable timestamp" in r.detail


def test_manual_rollback_check_fails_closed_on_an_unparseable_rollback_timestamp(tmp_path):
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="not-a-timestamp")
    _write_smoke_result(tmp_path, success=True, checked_at="2026-09-15T09:05:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "missing a parseable timestamp" in r.detail


def test_manual_rollback_check_passes_when_the_last_manual_entry_was_refused(tmp_path):
    """Code review (e4-checks-deploy-changelog): ``rollback_report.refused()``
    records ``mutated: False`` — a rollback stopped before changing anything
    (missing ``--clone-name``, invalid ``--target-ref``, unreadable
    ``--profile``). It has nothing to prove alive; demanding a liveness
    check for it is a false failure the operator can only clear by running
    an unnecessary smoke test.
    """
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00", mutated=False)
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is True, r.detail


def test_manual_rollback_check_still_demands_liveness_after_a_refused_entry(tmp_path):
    """A refused (mutated=False) manual entry must not mask an EARLIER real
    (mutated=True) manual rollback that still has no liveness evidence."""
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T08:00:00+00:00", mutated=True)
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00", mutated=False)
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "no liveness check has been recorded" in r.detail


def test_parse_iso_utc_fails_closed_on_a_naive_timestamp_instead_of_guessing_utc(tmp_path):
    """Doubt review (e4-checks-deploy-changelog): an earlier fix coerced a
    naive timestamp (no offset — a plausible hand-written
    phase_history[deploy].at) to UTC on the theory that the alternative was
    an uncontained crash. It wasn't — a raise here is already caught one
    layer up (validation_record.py) and surfaced as a fail-closed ask-level
    gate error — and for a naive value actually written in a non-UTC local
    zone, guessing UTC reads the instant hours away from reality, which can
    make a STALE entry appear fresh. An unknown-zone timestamp must be
    treated as unparseable, not guessed.
    """
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00")
    _write_smoke_result(tmp_path, success=True, checked_at="2026-09-15T09:05:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is False
    assert "missing a parseable timestamp" in r.detail


def test_last_jsonl_entry_tolerates_blank_and_malformed_lines(tmp_path):
    """``_last_jsonl_entry`` (used by the manual-rollback check above) must
    skip a blank line, a line that isn't valid JSON, and a line that parses
    to something other than an object — never crash, and still find the
    real entry that follows.
    """
    history = tmp_path / ".shipwright" / "deploy" / "rollback-history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        "\n"
        "{not valid json\n"
        "[1, 2, 3]\n"
        + json.dumps({"invocation": "manual", "recorded_at": "2026-09-15T09:00:00+00:00",
                      "success": True}) + "\n",
        encoding="utf-8",
    )
    _write_smoke_result(tmp_path, success=True, checked_at="2026-09-15T09:05:00+00:00")
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is True


def test_last_jsonl_entry_returns_none_on_an_unreadable_file(tmp_path, monkeypatch):
    """An OSError while reading the JSONL (permissions, a transient FS
    error) must degrade to "no entry found", never crash the check."""
    _write_rollback_entry(tmp_path, invocation="manual", recorded_at="2026-09-15T09:00:00+00:00")

    real_read_text = Path.read_text

    def _raise_on_history(self, *args, **kwargs):
        if self.name == "rollback-history.jsonl":
            raise OSError("simulated unreadable file")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _raise_on_history)
    r = check_manual_rollback_proves_alive(tmp_path)
    assert r.ok is True
    assert "no operator-requested rollback recorded yet" in r.detail


# --------------------------------------------------------------------------
# Deliberate constant duplication (ADR-045) — pin the twin, don't import it
# --------------------------------------------------------------------------

def test_the_rollback_history_path_literal_matches_its_plugin_local_twin():
    """``deploy_checks._ROLLBACK_HISTORY_RELATIVE`` is a deliberate literal
    duplicate of ``rollback_audit.HISTORY_RELATIVE_PATH`` (ADR-045: no
    cross-plugin ``lib/`` import from this shared/generic module). External
    review (round 1, e4-checks-deploy-changelog) flagged that two
    independently-maintained copies of a path constant drift silently. Read
    the plugin-local module as TEXT rather than importing it, so this stays
    a shared/tests-only check with no plugin-package sys.path exposure.
    """
    from tools.verifiers.deploy_checks import _ROLLBACK_HISTORY_RELATIVE, _SMOKE_RESULT_RELATIVE

    plugin_lib = (
        Path(__file__).resolve().parent.parent.parent
        / "plugins" / "shipwright-deploy" / "scripts" / "lib" / "rollback_audit.py"
    )
    source = plugin_lib.read_text(encoding="utf-8")
    # rollback_audit.py builds its constant as `Path(".shipwright") / "deploy"
    # / "rollback-history.jsonl"` — each quoted segment joined by `/`, not one
    # joined string. A three-independent-substrings check (round 1 of this
    # test) would pass even if the segments appeared unrelated to each other
    # elsewhere in the file (GLM, external code review round 2) — requiring
    # them adjacent, in order, joined by `/` on one `Path(...)` expression is
    # closer to actually parsing the real construct without an AST parser.
    segments = _ROLLBACK_HISTORY_RELATIVE.parts
    pattern = r"Path\(" + r"\)\s*/\s*".join(f'"{re.escape(s)}"' for s in segments[:1])
    pattern += r"\)" + "".join(rf'\s*/\s*"{re.escape(s)}"' for s in segments[1:])
    assert re.search(pattern, source), (
        f"deploy_checks._ROLLBACK_HISTORY_RELATIVE={_ROLLBACK_HISTORY_RELATIVE!s} has no "
        f"matching `Path(...) / ... ` expression in rollback_audit.py (pattern {pattern!r}) "
        "— the two copies have drifted"
    )
    # The smoke-result twin lives in the SKILL.md prose (`--output`), not a
    # Python constant — checked separately by the SKILL.md's own content.
    assert str(_SMOKE_RESULT_RELATIVE).replace("\\", "/") == ".shipwright/deploy/smoke-test-result.json"
