"""Tests for ``check_e2e_counts_reconciled`` (FR-01.06 #5,
sub-iterate ``e3-checks-test-security``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verifiers._test_gate_extras import check_e2e_counts_reconciled


def _write_pw_results(root: Path, stats: dict) -> None:
    (root / "e2e-results.json").write_text(json.dumps({"stats": stats}))


def _write_test_results(root: Path, e2e: dict | None) -> None:
    payload = {} if e2e is None else {"e2e": e2e}
    (root / "shipwright_test_results.json").write_text(json.dumps(payload))


def test_skips_when_no_playwright_results(tmp_path):
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.is_skipped
    assert "not run" in r.detail


def test_fails_when_test_results_missing_but_playwright_present(tmp_path):
    _write_pw_results(tmp_path, {"expected": 1, "unexpected": 0, "skipped": 0, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "missing" in r.detail


def test_fails_on_malformed_test_results(tmp_path):
    _write_pw_results(tmp_path, {"expected": 1, "unexpected": 0, "skipped": 0, "flaky": 0})
    (tmp_path / "shipwright_test_results.json").write_text("{not json")
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "malformed" in r.detail


def test_fails_on_missing_e2e_layer(tmp_path):
    _write_pw_results(tmp_path, {"expected": 1, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, None)
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "no e2e layer" in r.detail


def test_skips_when_e2e_layer_recorded_skipped_and_no_playwright_evidence(tmp_path):
    _write_test_results(tmp_path, {"skipped": True})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.is_skipped


def test_skips_when_e2e_layer_recorded_skipped_and_evidence_is_genuinely_zero(tmp_path):
    _write_pw_results(tmp_path, {"expected": 0, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"skipped": True})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.is_skipped


def test_fails_when_skipped_claim_is_contradicted_by_playwright_evidence(tmp_path):
    """External review round 2 (GLM, medium): a recorded `e2e.skipped: true`
    while e2e-results.json shows the tool actually ran is the same
    fabrication/staleness class this check exists to catch."""
    _write_pw_results(tmp_path, {"expected": 1, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"skipped": True})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "contradicts" in r.detail


def test_fails_on_malformed_playwright_results(tmp_path):
    (tmp_path / "e2e-results.json").write_text("{not json")
    _write_test_results(tmp_path, {"total": 1, "passed": 1, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "malformed e2e-results.json" in r.detail


def test_fails_on_missing_stats_block(tmp_path):
    (tmp_path / "e2e-results.json").write_text(json.dumps({"suites": []}))
    _write_test_results(tmp_path, {"total": 1, "passed": 1, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "no stats block" in r.detail


def test_passes_when_counts_match(tmp_path):
    """External review round 2 (GLM, low): the severity assertion here used
    to pin an implementation detail (the default severity on a PASSING
    result) unrelated to this criterion and asymmetric with the failure
    paths below, which assert none. Dropped — only the outcome matters."""
    _write_pw_results(tmp_path, {"expected": 3, "unexpected": 1, "skipped": 1, "flaky": 1})
    # total = 3+1+1+1 = 6; passed = 3+1 = 4; flaky = 1
    _write_test_results(tmp_path, {"total": 6, "passed": 4, "flaky": 1})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is True


def test_fails_when_total_diverges(tmp_path):
    _write_pw_results(tmp_path, {"expected": 3, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"total": 5, "passed": 3, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "total: recorded=5 tool=3" in r.detail


def test_fails_when_passed_diverges(tmp_path):
    _write_pw_results(tmp_path, {"expected": 3, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"total": 3, "passed": 2, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "passed: recorded=2 tool=3" in r.detail


def test_fails_when_flaky_diverges(tmp_path):
    _write_pw_results(tmp_path, {"expected": 2, "unexpected": 0, "skipped": 0, "flaky": 1})
    _write_test_results(tmp_path, {"total": 3, "passed": 3, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "flaky: recorded=0 tool=1" in r.detail


def test_recorded_bool_total_is_reported_as_malformed_not_coerced(tmp_path):
    """Tier-3 CI review (PR #748): `bool` is an `int` subclass in Python, so
    a recorded `total: true` compares equal to an expected total of 1 with
    plain `!=` — a malformed recorded count must not silently "reconcile"
    against a numerically-equal expected value."""
    _write_pw_results(tmp_path, {"expected": 1, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"total": True, "passed": 1, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "total=True is not a non-negative integer" in r.detail


def test_bool_stats_are_reported_as_malformed_not_coerced(tmp_path):
    """A hand-edited stats block with `true`/`false` in place of an int must
    not silently be treated as 1/0 (bool is an int subclass in Python) NOR
    silently coerced to 0 — external review (both reviewers, medium): a
    silent-0 coercion let a malformed stats block reconcile falsely against
    a hand-written zero-count record. It must FAIL with a distinct
    diagnostic instead."""
    _write_pw_results(tmp_path, {"expected": True, "unexpected": False, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"total": 0, "passed": 0, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "unrecognized/malformed" in r.detail
    assert "expected=True" in r.detail
    assert "unexpected=False" in r.detail


def test_negative_stat_is_reported_as_malformed(tmp_path):
    _write_pw_results(tmp_path, {"expected": -1, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"total": 0, "passed": 0, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "expected=-1" in r.detail


def test_string_stat_is_reported_as_malformed(tmp_path):
    _write_pw_results(tmp_path, {"expected": "3", "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"total": 3, "passed": 3, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "expected='3'" in r.detail


def test_absent_stats_field_still_defaults_to_zero(tmp_path):
    """An honestly-absent field (some reporter versions omit zero-count
    fields) is unchanged behavior — only a PRESENT-but-invalid value is an
    error."""
    _write_pw_results(tmp_path, {"expected": 2, "unexpected": 0})
    _write_test_results(tmp_path, {"total": 2, "passed": 2, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is True


def test_missing_flaky_field_defaults_to_zero(tmp_path):
    _write_pw_results(tmp_path, {"expected": 2, "unexpected": 0, "skipped": 0, "flaky": 0})
    _write_test_results(tmp_path, {"total": 2, "passed": 2})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is True


def test_fails_not_skips_when_e2e_recorded_but_playwright_evidence_missing(tmp_path):
    """External Tier-3 review (PR for e3-checks-test-security): the original
    ordering SKIPPED here (no e2e-results.json -> nothing to reconcile),
    letting a fabricated or stale e2e block sail through unverified. A
    recorded, non-skipped e2e layer with no evidence file must FAIL."""
    _write_test_results(tmp_path, {"total": 5, "passed": 5, "flaky": 0})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "cannot be verified" in r.detail


def test_skips_when_neither_file_exists(tmp_path):
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.is_skipped


def test_symlinked_test_results_escaping_root_fails_as_missing_not_the_outside_content(tmp_path):
    """External review (low): the previous version of this test accepted
    EITHER a SKIP or a FAIL outcome, so it could not detect a regression
    between the two, and its name/docstring claimed SKIP when the actual
    code path (pw_path present, results_path treated as missing) produces
    FAIL. Pin the exact outcome instead."""
    outside = tmp_path.parent / "outside_e2e_reconciliation_target.json"
    outside.write_text(json.dumps({"e2e": {"total": 999, "passed": 999, "flaky": 0}}))
    try:
        (tmp_path / "shipwright_test_results.json").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        _write_pw_results(tmp_path, {"expected": 1, "unexpected": 0, "skipped": 0, "flaky": 0})
        r = check_e2e_counts_reconciled(tmp_path)
        # A symlinked shipwright_test_results.json escaping the project root
        # is treated as "missing"; since e2e-results.json IS present, that
        # combination is the same "evidence exists, record doesn't" FAIL
        # path as test_fails_when_test_results_missing_but_playwright_present
        # — never as if the outside file's 999/999 were this project's own
        # record.
        assert r.ok is False
        assert "missing" in r.detail
    finally:
        outside.unlink(missing_ok=True)


def test_int_skipped_count_does_not_masquerade_as_a_skipped_layer(tmp_path):
    """HIGH (Stage-2 code-reviewer, 2026-09-12): `skipped` is overloaded.
    `playwright_runner.parse_playwright_json` writes it as a COUNT of
    skipped tests in a layer that ran; only the boolean means the layer
    itself did not run. Under the original truthiness test, an honest run
    with >=1 skipped test was read as a skipped LAYER and then hard-failed
    as a 'skipped claim the tool's own output contradicts' — a fabrication
    accusation against a correct record."""
    _write_pw_results(tmp_path, {"expected": 17, "unexpected": 0, "skipped": 3, "flaky": 0})
    _write_test_results(tmp_path, {"skipped": 3, "total": 20, "passed": 17})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is True
    assert not r.is_skipped
    assert "matches playwright's own stats" in r.detail


def test_int_skipped_count_still_reconciles_strictly(tmp_path):
    """The same record with counts that do NOT match the tool still fails —
    the fix restores the reconciliation, it does not weaken it."""
    _write_pw_results(tmp_path, {"expected": 17, "unexpected": 0, "skipped": 3, "flaky": 0})
    _write_test_results(tmp_path, {"skipped": 3, "total": 20, "passed": 20})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.ok is False
    assert "passed: recorded=20 tool=17" in r.detail


def test_boolean_skipped_layer_is_still_honoured(tmp_path):
    """The boolean meaning is unchanged: a layer marked `skipped: true` with
    no contradicting evidence still SKIPS rather than demanding counts."""
    _write_test_results(tmp_path, {"skipped": True})
    r = check_e2e_counts_reconciled(tmp_path)
    assert r.is_skipped
    assert "nothing to reconcile" in r.detail
