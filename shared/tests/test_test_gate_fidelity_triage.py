"""Tests for ``check_design_fidelity_triage_matches_recomputation`` and its
pure ``_categorize_fidelity_screen`` helper (FR-01.06 #7, mechanisable half,
sub-iterate ``e3-checks-test-security``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verifiers._test_gate_fidelity import (
    _categorize_fidelity_screen,
    check_design_fidelity_triage_matches_recomputation,
)


def _write_build_report(root: Path, screens: dict) -> None:
    (root / "design-fidelity-report.json").write_text(
        json.dumps({"build_complete": True, "screens": screens})
    )


def _write_test_results(root: Path, design_fidelity: dict | None) -> None:
    payload = {} if design_fidelity is None else {"design_fidelity": design_fidelity}
    (root / "shipwright_test_results.json").write_text(json.dumps(payload))


# --- _categorize_fidelity_screen: the pure table ----------------------------

def test_categorize_resolved():
    assert _categorize_fidelity_screen("partial", "pass") == "resolved"


def test_categorize_pass_with_full_build_is_not_triaged():
    assert _categorize_fidelity_screen("full", "pass") is None


def test_categorize_pass_with_unknown_build_is_not_triaged():
    assert _categorize_fidelity_screen(None, "pass") is None


def test_categorize_regression():
    assert _categorize_fidelity_screen("full", "needs_review") == "regression"


def test_categorize_persistent_failure():
    assert _categorize_fidelity_screen("partial", "needs_review") == "persistent_failure"


def test_categorize_unchecked_when_absent_from_build_report():
    assert _categorize_fidelity_screen(None, "needs_review") == "unchecked"


def test_categorize_unchecked_when_build_skipped_it():
    assert _categorize_fidelity_screen("skipped", "needs_review") == "unchecked"


def test_categorize_error_status_out_of_scope():
    assert _categorize_fidelity_screen("full", "error") is None
    assert _categorize_fidelity_screen(None, "error") is None


def test_categorize_pass_with_skipped_build_is_not_triaged():
    """External review (low): asymmetric with (`"full"`, `"pass"`) — both
    correctly fall out of the table (only a build-time `"partial"` resolves
    to `"resolved"`), but only the `full` case had a test before."""
    assert _categorize_fidelity_screen("skipped", "pass") is None


# --- check_design_fidelity_triage_matches_recomputation ---------------------

def test_skips_when_no_build_report(tmp_path):
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.is_skipped


def test_fails_when_test_results_missing(tmp_path):
    _write_build_report(tmp_path, {})
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "missing" in r.detail


def test_fails_on_malformed_build_report(tmp_path):
    (tmp_path / "design-fidelity-report.json").write_text("{not json")
    _write_test_results(tmp_path, {"screens": [], "triage": {}})
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "malformed design-fidelity-report.json" in r.detail


def test_fails_on_malformed_test_results(tmp_path):
    _write_build_report(tmp_path, {})
    (tmp_path / "shipwright_test_results.json").write_text("{not json")
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "malformed shipwright_test_results.json" in r.detail


def test_skips_when_no_design_fidelity_block(tmp_path):
    _write_build_report(tmp_path, {})
    _write_test_results(tmp_path, None)
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.is_skipped


def test_skips_when_no_triage_block(tmp_path):
    _write_build_report(tmp_path, {})
    _write_test_results(tmp_path, {"screens": [{"mockup": "01-login.html", "status": "pass"}]})
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.is_skipped


def test_fails_when_whole_design_fidelity_block_absent_but_build_declares_screens(tmp_path):
    """External review round 2 (openai, medium): a build report that DOES
    declare screens combined with a test-time record that omits the WHOLE
    `design_fidelity` block (not just `triage`) means the comparison step
    never ran at all — must FAIL, not SKIP on the strength of the build
    side alone having done work."""
    _write_build_report(tmp_path, {"01-login.html": {"status": "partial"}})
    _write_test_results(tmp_path, None)
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "comparison step never ran" in r.detail


def test_fails_when_triage_block_absent_but_recomputation_finds_screens_needing_it(tmp_path):
    """HIGH (openai, external code review): the original ordering SKIPPED
    whenever `triage` was absent, REGARDLESS of whether the recomputation
    would find screens needing triage — a `needs_review` screen with no
    triage entry evaded the gate entirely by simply omitting the block,
    exactly the 'regression == never-checked' gap this criterion forbids."""
    _write_build_report(tmp_path, {"02-dash.html": {"status": "full"}})
    _write_test_results(tmp_path, {
        "screens": [{"mockup": "02-dash.html", "status": "needs_review"}],
        # no "triage" key at all
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "no triage block was recorded" in r.detail


def test_passes_when_triage_matches_recomputation(tmp_path):
    _write_build_report(tmp_path, {
        "01-login.html": {"status": "partial"},   # resolved (now passes)
        "02-dash.html": {"status": "full"},        # regression (now needs review)
        "03-settings.html": {"status": "partial"}, # persistent failure
        # 04-billing.html absent from build report -> unchecked
    })
    _write_test_results(tmp_path, {
        "screens": [
            {"mockup": "01-login.html", "status": "pass"},
            {"mockup": "02-dash.html", "status": "needs_review"},
            {"mockup": "03-settings.html", "status": "needs_review"},
            {"mockup": "04-billing.html", "status": "needs_review"},
        ],
        "triage": {
            "resolved": 1, "regressions": 1,
            "persistent_failures": 1, "unchecked": 1,
        },
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is True


def test_fails_when_recorded_triage_undercounts_regressions(tmp_path):
    _write_build_report(tmp_path, {"02-dash.html": {"status": "full"}})
    _write_test_results(tmp_path, {
        "screens": [{"mockup": "02-dash.html", "status": "needs_review"}],
        "triage": {"resolved": 0, "regressions": 0, "persistent_failures": 0, "unchecked": 0},
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is False
    assert "regressions: recorded=0 recomputed=1" in r.detail


def test_error_status_screens_excluded_from_recomputation(tmp_path):
    """A screen the compare tool could not even resolve an implementation
    file for (`status: error`) is not part of the triage table at all —
    a recorded all-zero triage must still pass."""
    _write_build_report(tmp_path, {})
    _write_test_results(tmp_path, {
        "screens": [{"mockup": "missing.html", "status": "error", "error": "no route"}],
        "triage": {"resolved": 0, "regressions": 0, "persistent_failures": 0, "unchecked": 0},
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is True


def test_non_dict_screen_entries_are_ignored(tmp_path):
    _write_build_report(tmp_path, {})
    _write_test_results(tmp_path, {
        "screens": ["not-a-dict", 42, None],
        "triage": {"resolved": 0, "regressions": 0, "persistent_failures": 0, "unchecked": 0},
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is True


def test_non_string_mockup_key_is_treated_as_unmatched(tmp_path):
    _write_build_report(tmp_path, {"01-login.html": {"status": "full"}})
    _write_test_results(tmp_path, {
        "screens": [{"mockup": 123, "status": "needs_review"}],
        "triage": {"resolved": 0, "regressions": 0, "persistent_failures": 0, "unchecked": 1},
    })
    r = check_design_fidelity_triage_matches_recomputation(tmp_path)
    assert r.ok is True


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
