"""Regression tests for the ``resolved``-obligation narrowing (Stage-2
code-reviewer HIGH finding) and the Tier-3 CI review hardening (malformed
screen data, escaping symlinks) in
``check_design_fidelity_triage_matches_recomputation`` (FR-01.06 #7,
sub-iterate ``e3-checks-test-security``). Split out of
``test_test_gate_fidelity_triage.py`` when that file crossed 300 lines a
second time (round 5, Tier-3 CI review on PR #748); the fixture helpers below
are shared back with it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verifiers._test_gate_fidelity import check_design_fidelity_triage_matches_recomputation


def _write_build_report(root: Path, screens: dict) -> None:
    (root / "design-fidelity-report.json").write_text(
        json.dumps({"build_complete": True, "screens": screens})
    )


def _write_test_results(root: Path, design_fidelity: dict | None) -> None:
    payload = {} if design_fidelity is None else {"design_fidelity": design_fidelity}
    (root / "shipwright_test_results.json").write_text(json.dumps(payload))


def test_malformed_build_screens_value_fails_closed(tmp_path):
    """Tier-3 CI review (PR #748): a `screens` field that IS present but is
    not an object is a malformed report, not an empty one — silently
    coercing it to `{}` let a fabricated/corrupted build report masquerade
    as "no screens declared" and pass whatever the test side claimed."""
    (tmp_path / "design-fidelity-report.json").write_text(
        json.dumps({"screens": "not-a-dict"})
    )
    _write_test_results(tmp_path, {
        "screens": [{"mockup": "01-login.html", "status": "needs_review"}],
        "triage": {"resolved": 0, "regressions": 0, "persistent_failures": 0, "unchecked": 1},
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "screens field is a str" in r.detail


def test_resolved_only_needs_no_triage_block(tmp_path):
    """HIGH (Stage-2 code-reviewer, 2026-09-12): the no-triage-block branch
    measured the obligation over EVERY recomputed count, `resolved`
    included. A run whose only fidelity movement is an improvement —
    partial at build time, pass now — then FAILED with a message claiming a
    `needs_review` screen existed when none did. Improvement owes no triage
    entry; only regressions/persistent failures/unchecked screens do."""
    _write_build_report(tmp_path, {
        "01-login.html": {"status": "partial"},
        "02-dash.html": {"status": "partial"},
    })
    _write_test_results(tmp_path, {
        "screens": [
            {"mockup": "01-login.html", "status": "pass"},
            {"mockup": "02-dash.html", "status": "pass"},
        ],
        # no "triage" key — correct, nothing needed triaging
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is True
    assert r.is_skipped
    assert "passed or improved" in r.detail


def test_resolved_alongside_a_regression_still_obliges_a_triage_block(tmp_path):
    """The narrowing must not let a real gap through: a `resolved` screen
    sitting next to a regression leaves the block obligatory, and the count
    reported is the one that needs triage (1), not the recomputed total (2)."""
    _write_build_report(tmp_path, {
        "01-login.html": {"status": "partial"},  # resolved
        "02-dash.html": {"status": "full"},      # regression
    })
    _write_test_results(tmp_path, {
        "screens": [
            {"mockup": "01-login.html", "status": "pass"},
            {"mockup": "02-dash.html", "status": "needs_review"},
        ],
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "found 1 screen(s) needing triage" in r.detail


def test_recorded_triage_block_must_still_get_resolved_right(tmp_path):
    """`resolved` is excluded from the OBLIGATION only. Once a triage block
    is recorded it is compared over all four keys, so a wrong `resolved`
    count is still a mismatch."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    _write_test_results(tmp_path, {
        "screens": [{"mockup": "01-login.html", "status": "pass"}],
        "triage": {
            "resolved": 0, "regressions": 0,
            "persistent_failures": 0, "unchecked": 0,
        },
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "resolved: recorded=0 recomputed=1" in r.detail


def test_escaping_report_symlink_fails_instead_of_skipping(tmp_path):
    """Tier-3 CI review (PR #748): a fixed-name artifact that exists but
    resolves outside the project root must FAIL, not SKIP the same as an
    honestly absent one — a SKIP would let a project-controlled symlink
    suppress this gate entirely."""
    outside = tmp_path.parent / "outside-design-fidelity-report.json"
    outside.write_text(json.dumps({"screens": {}}))
    try:
        (tmp_path / "design-fidelity-report.json").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "symlink escape" in r.detail


def test_missing_test_side_screens_with_declared_build_screens_fails(tmp_path):
    """Tier-3 CI review (PR #748): a fabricated all-zero triage block paired
    with a missing/malformed `design_fidelity.screens` must not pass just
    because the recomputation (over zero screens) happens to also be all
    zero — the build side declared real screens that were never actually
    compared."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    _write_test_results(tmp_path, {
        "screens": "not-a-list",
        "triage": {
            "resolved": 0, "regressions": 0,
            "persistent_failures": 0, "unchecked": 0,
        },
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "never actually covered them" in r.detail


def test_honest_skipped_layer_skips_even_with_declared_build_screens(tmp_path):
    """Stage-2 code-reviewer (2026-09-12, PR #748 re-review): the round-1
    Tier-3 fix above turned an honest could-not-run design_fidelity record
    (`skipped: true`, its own documented record-template flag — step-3.7-
    design-fidelity.md's own example JSON) into a false "fabrication" FAIL
    whenever the build side declared screens but the skipped record's
    `screens` list was absent or empty. A skipped layer owes nothing."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    _write_test_results(tmp_path, {"skipped": True})
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is True
    assert r.is_skipped


def test_skipped_layer_contradicted_by_real_screens_fails(tmp_path):
    """A `skipped: true` claim alongside real screens or a recorded triage
    block is the same fabrication/staleness class this check exists to
    catch — the same discipline check_e2e_counts_reconciled already applies
    to its own `e2e.skipped` field."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    _write_test_results(tmp_path, {
        "skipped": True,
        "screens": [{"mockup": "01-login.html", "status": "pass"}],
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "'skipped' claim its own record contradicts" in r.detail


def test_junk_screen_entries_with_declared_build_screens_fails(tmp_path):
    """Stage-2 code-reviewer (2026-09-12, PR #748 re-review): a non-empty
    `screens` list holding only junk (non-dict) entries is outcome-identical
    to the empty list the round-1 Tier-3 fix already closed — the
    recomputation over zero usable entries still reconciles with a
    fabricated all-zero triage block."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    _write_test_results(tmp_path, {
        "screens": ["not-a-dict", 42, None],
        "triage": {
            "resolved": 0, "regressions": 0,
            "persistent_failures": 0, "unchecked": 0,
        },
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "never actually covered them" in r.detail


def test_skipped_layer_with_malformed_screens_value_fails_not_skips(tmp_path):
    """Stage-2 code-reviewer (2026-09-12, PR #748 re-review): the honest-skip
    branch above only recognised a contradiction in a LIST `screens` value —
    a present-but-malformed one (a string, a dict, ...) fell through as "no
    real screens" and SKIPped, inconsistent with the non-skipped branch's own
    "malformed, not empty" discipline for the same field."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    _write_test_results(tmp_path, {"skipped": True, "screens": "not-a-list"})
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "malformed, not empty" in r.detail


def test_non_object_build_report_top_level_fails_closed(tmp_path):
    """Tier-3 CI review, round 3 (PR #748): a valid JSON document whose TOP
    LEVEL isn't an object (a list here) was silently read the same as "no
    screens field" and could sail through as an honestly empty report."""
    (tmp_path / "design-fidelity-report.json").write_text(json.dumps([1, 2, 3]))
    _write_test_results(tmp_path, {
        "screens": [{"mockup": "01-login.html", "status": "needs_review"}],
        "triage": {"resolved": 0, "regressions": 0, "persistent_failures": 0, "unchecked": 1},
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "top-level value is a list, not an object" in r.detail


def test_non_object_test_results_top_level_fails_closed(tmp_path):
    """Same class of gap as the build-report check above, for
    shipwright_test_results.json's own top-level shape."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps("not-an-object"))
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "top-level value is a str, not an object" in r.detail


def test_boolean_triage_counts_are_reported_as_malformed_not_coerced(tmp_path):
    """Tier-3 CI review, round 3 (PR #748): `bool` is an `int` subclass in
    Python, so a recorded `true`/`false` would compare equal to the
    recomputed `1`/`0` and silently pass a fabricated or corrupted triage
    block instead of being caught as malformed."""
    _write_build_report(tmp_path, {
        "01-login.html": {"status": "full"},
    })
    _write_test_results(tmp_path, {
        "screens": [{"mockup": "01-login.html", "status": "needs_review"}],
        "triage": {
            "resolved": 0, "regressions": True,
            "persistent_failures": 0, "unchecked": 0,
        },
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "not a non-negative integer" in r.detail


def test_invalid_utf8_build_report_fails_as_malformed_not_crashed(tmp_path):
    """Tier-3 CI review (PR #748, round 6): UnicodeDecodeError is a
    ValueError, not an OSError, so design-fidelity-report.json with invalid
    UTF-8 bytes used to crash the whole gate instead of returning a
    malformed CheckResult like any other unreadable file."""
    (tmp_path / "design-fidelity-report.json").write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    _write_test_results(tmp_path, None)
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "malformed design-fidelity-report.json" in r.detail


def test_invalid_utf8_test_results_fails_as_malformed_not_crashed(tmp_path):
    """Same class of gap for the sibling shipwright_test_results.json read."""
    _write_build_report(tmp_path, {})
    (tmp_path / "shipwright_test_results.json").write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "malformed shipwright_test_results.json" in r.detail
