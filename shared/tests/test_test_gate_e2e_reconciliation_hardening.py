"""Symlink-escape regression tests for ``check_e2e_counts_reconciled``
(FR-01.06 #5, sub-iterate ``e3-checks-test-security``). Split out of
``test_test_gate_e2e_reconciliation.py`` when that file crossed 300 lines
(round 6, Stage-2 code-reviewer re-review of PR #748); the fixture helpers
below are shared back with it.
"""

from __future__ import annotations

import json

import pytest

from tools.verifiers._test_gate_extras import check_e2e_counts_reconciled

from .test_test_gate_e2e_reconciliation import _write_pw_results, _write_test_results


def test_symlinked_test_results_escaping_root_fails_as_an_escape_not_the_outside_content(tmp_path):
    """External review (low): the previous version of this test accepted
    EITHER a SKIP or a FAIL outcome, so it could not detect a regression
    between the two. Stage-2 code-reviewer (2026-09-12, PR #748 re-review):
    an escaping symlink folded into the same "missing" path as a genuinely
    absent file, the same class of gap the Tier-3 CI review already closed
    for design-fidelity-report.json — never as if the outside file's
    999/999 were this project's own record."""
    outside = tmp_path.parent / "outside_e2e_reconciliation_target.json"
    outside.write_text(json.dumps({"e2e": {"total": 999, "passed": 999, "flaky": 0}}))
    try:
        (tmp_path / "shipwright_test_results.json").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        _write_pw_results(tmp_path, {"expected": 1, "unexpected": 0, "skipped": 0, "flaky": 0})
        r = check_e2e_counts_reconciled(tmp_path)
        assert r.ok is False
        assert "symlink escape" in r.detail
    finally:
        outside.unlink(missing_ok=True)


def test_symlinked_pw_results_escaping_root_fails_as_an_escape(tmp_path):
    """Same class of gap as the shipwright_test_results.json escape above,
    for the sibling e2e-results.json read."""
    outside = tmp_path.parent / "outside_pw_results_target.json"
    outside.write_text(json.dumps({"stats": {"expected": 999, "unexpected": 0, "skipped": 0, "flaky": 0}}))
    try:
        (tmp_path / "e2e-results.json").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        _write_test_results(tmp_path, {"total": 1, "passed": 1, "flaky": 0})
        r = check_e2e_counts_reconciled(tmp_path)
        assert r.ok is False
        assert "symlink escape" in r.detail
    finally:
        outside.unlink(missing_ok=True)


def test_skipped_layer_contradiction_check_not_defeated_by_an_escaping_pw_results(tmp_path):
    """A `skipped: true` claim contradicted by real evidence must not be
    defeatable by symlinking e2e-results.json outside the project root —
    an escape must FAIL outright, the same as the fidelity gate's own
    skipped-flag branch, rather than silently reading as "no evidence, no
    contradiction" (pw_path folded to None) and letting the SKIP through."""
    outside = tmp_path.parent / "outside_pw_results_for_skipped_claim.json"
    outside.write_text(json.dumps({"stats": {"expected": 5, "unexpected": 0, "skipped": 0, "flaky": 0}}))
    try:
        (tmp_path / "e2e-results.json").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        _write_test_results(tmp_path, {"skipped": True})
        r = check_e2e_counts_reconciled(tmp_path)
        assert r.ok is False
        assert "symlink escape" in r.detail
    finally:
        outside.unlink(missing_ok=True)
