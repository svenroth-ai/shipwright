"""The /shipwright-test design-fidelity triage gate (FR-01.06 #7, mechanisable
half), split out of ``_test_gate_extras.py`` the moment that file crossed 300
lines with all three gates. Sub-iterate ``e3-checks-test-security``,
``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``.

:func:`check_design_fidelity_triage_matches_recomputation` — **#7**
(mechanisable half) "screens compared back to mockups; regression != never-
checked." The structural compare (``design_fidelity_check.py``) is already
enforced+tested. What the ledger names as "agent judgement" is
step-3.7's Resolved / Regression / Persistent Failure / Unchecked table —
but that table is a **pure function of two already-recorded values** (the
screen's build-time status and its current status), not a judgement call.
:func:`_categorize_fidelity_screen` is that pure function; the check
recomputes the whole ``design_fidelity.triage`` block from the two source
files (``design-fidelity-report.json`` written by build,
``shipwright_test_results.json``'s ``design_fidelity.screens`` written by
test) and fails when the RECORDED triage summary disagrees — catching a
miscounted or fabricated triage report the same way ``check_test_results_
file_fresh`` catches a miscounted unit-test gap.

**Known, accepted limitation** (external review): the two source files carry
no shared run/build identifier, so a STALE ``design-fidelity-report.json``
from an earlier build combined with a fresh test run can disagree with the
recorded triage for a reason that is not "the record is wrong" —
"regenerate one of the two artifacts" is equally likely. Adding real
provenance (a run id on the build-side writer,
``plugins/shipwright-build/scripts/tools/update_section_state.py``) is a
producer-side change outside a checks-only sub-iterate's scope; the failure
detail names both source files so an operator investigates the right two
things rather than assuming the newer one is correct.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._test_gate_paths import _project_file_or_escape, _safe_project_file
from ._test_gate_fidelity_categorize import (
    TRIAGE_RECORD_KEYS as _TRIAGE_RECORD_KEYS,
    TRIAGE_REQUIRING_KEYS as _TRIAGE_REQUIRING_KEYS,
    categorize_fidelity_screen as _categorize_fidelity_screen,
    validate_triage_counts as _validate_triage_counts,
)
from .common import CheckResult, Severity


def check_design_fidelity_triage_matches_recomputation(project_root: Path) -> CheckResult:
    """FR-01.06 #7 (mechanisable half): the Resolved/Regression/Persistent
    Failure/Unchecked triage recorded in ``shipwright_test_results.json``'s
    ``design_fidelity.triage`` must match a mechanical recomputation from the
    two files it is derived from.

    SKIPPED when there is nothing to recompute: no build-time
    ``design-fidelity-report.json``, OR one with an empty/absent ``screens``
    dict (no UI screens this project) even if ``design_fidelity`` is also
    absent at test time; OR ``design_fidelity.skipped is True`` (the record
    template's own boolean flag for "this layer never ran", uncontradicted by
    real screens or a recorded triage block); OR a recomputation that finds
    ZERO screens needing triage — every screen either passed outright or
    IMPROVED (``resolved``: partial at build time, pass now), so step 3.7
    never entered the triage branch and a missing ``triage`` block is
    correct, not a gap. ``resolved`` is the reason the obligation is measured
    over ``_TRIAGE_REQUIRING_KEYS`` rather than over every count: a run whose
    only movement is improvement owes nothing, and failing it would be a
    pure false alarm.

    Several distinct FAIL cases guard against a fabricated or incomplete
    comparison rather than an honestly empty one: a symlinked
    ``design-fidelity-report.json`` escaping the project root (Tier-3 CI
    review, PR #748); either source file's ``screens`` field present but
    not the expected type (malformed, not empty); a build report that DOES
    declare screens combined with test-time recording NO ``design_fidelity``
    block, or one whose ``screens`` list is missing/malformed/empty, means
    the comparison step never actually covered them — caught before ever
    reaching the recomputation. A ``design_fidelity`` block that IS present
    but omits ``triage`` while the recomputation finds screens that DO need
    one FAILS too — letting "regression" and "never-checked" both escape the
    gate by simply omitting the block.
    """
    name = "design fidelity triage matches a mechanical recomputation"
    report_path, report_escaped = _project_file_or_escape(project_root, "design-fidelity-report.json")
    if report_escaped:
        # Tier-3 CI review (PR #748): a fixed-name artifact that exists but
        # resolves outside the project root must not be treated the same as
        # an honestly absent one — that would let a project-controlled
        # symlink suppress this gate (SKIP) instead of failing it, defeating
        # the whole point of enforcing the check.
        return CheckResult(
            name, False,
            "design-fidelity-report.json exists but resolves outside the "
            "project root (symlink escape) — treated as a suppression "
            "attempt, not an absent artifact",
        )
    if report_path is None:
        return CheckResult(
            name, True, "no design-fidelity-report.json — nothing to recompute",
            severity=Severity.SKIPPED.value,
        )

    results_path = _safe_project_file(project_root, "shipwright_test_results.json")
    if results_path is None:
        return CheckResult(
            name, False,
            "design-fidelity-report.json exists but shipwright_test_results.json is "
            "missing or unreadable",
        )

    try:
        build_report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed design-fidelity-report.json: {exc}")
    if not isinstance(build_report, dict):
        # Tier-3 CI review, round 3 (PR #748): a valid JSON document whose
        # TOP LEVEL isn't an object (a list, a string, a bare number, ...)
        # was silently treated the same as "no screens field" below and
        # could sail through as an empty, legitimate report.
        return CheckResult(
            name, False,
            f"design-fidelity-report.json's top-level value is a "
            f"{type(build_report).__name__}, not an object",
        )
    raw_build_screens = build_report.get("screens")
    if raw_build_screens is None:
        # A genuinely absent `screens` key means the report legitimately
        # declares no UI screens — a real empty state, not a schema error.
        build_screens = {}
    elif isinstance(raw_build_screens, dict):
        build_screens = raw_build_screens
    else:
        # Tier-3 CI review (PR #748): a `screens` field that IS present but
        # is not an object (a list, a string, ...) is a malformed report,
        # not an empty one — silently coercing it to `{}` let a fabricated
        # or corrupted build report masquerade as "no screens declared".
        return CheckResult(
            name, False,
            f"design-fidelity-report.json's screens field is a "
            f"{type(raw_build_screens).__name__}, not an object",
        )

    try:
        recorded = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed shipwright_test_results.json: {exc}")
    if not isinstance(recorded, dict):
        # Tier-3 CI review, round 3 (PR #748): same class of gap as the
        # build report above — a valid JSON document whose top level isn't
        # an object was silently read the same as "no design_fidelity key",
        # letting a schema error masquerade as an honest absence.
        return CheckResult(
            name, False,
            f"shipwright_test_results.json's top-level value is a "
            f"{type(recorded).__name__}, not an object",
        )

    design_fidelity = recorded.get("design_fidelity")
    if not isinstance(design_fidelity, dict):
        # External review round 2 (openai, medium): a build report that
        # DOES declare screens, combined with a test-time record that omits
        # the whole `design_fidelity` block, means the comparison step
        # never ran at all — a bigger omission than a missing `triage`
        # sub-block, and it must not SKIP silently on the strength of the
        # build side alone having done work.
        if build_screens:
            return CheckResult(
                name, False,
                f"design-fidelity-report.json declares {len(build_screens)} "
                f"screen(s), but shipwright_test_results.json has no "
                f"design_fidelity block at all — the comparison step never ran",
            )
        return CheckResult(
            name, True, "no design_fidelity block recorded — nothing to recompute",
            severity=Severity.SKIPPED.value,
        )

    if design_fidelity.get("skipped") is True:
        # Tier-3 CI review, round 2 (Stage-2 code-reviewer, PR #748): the
        # record template documents a first-class boolean `skipped` flag
        # meaning "this layer never ran" (step-3.7-design-fidelity.md's own
        # example JSON), the same overload check_e2e_counts_reconciled
        # already honours for its `e2e.skipped` field
        # (warning_followups.py's `_layer` names the bool-vs-count split
        # explicitly). The round-1 fix below must not turn this honest
        # could-not-run outcome into a false "fabrication" FAIL just
        # because its `screens` list is empty or absent. A `skipped: true`
        # claim contradicted by real screens or a recorded triage block is
        # still the fabrication/staleness class this check exists to catch.
        screens_claim = design_fidelity.get("screens")
        if screens_claim is not None and not isinstance(screens_claim, list):
            # Stage-2 code-reviewer (2026-09-12, PR #748 re-review): a
            # present-but-malformed `screens` value must FAIL here too, the
            # same "malformed, not empty" discipline the non-skipped branch
            # below already applies — otherwise this branch alone would
            # treat a corrupted record identically to an honestly-absent one.
            return CheckResult(
                name, False,
                "design_fidelity recorded as skipped, but its screens field "
                f"is a {type(screens_claim).__name__}, not a list — "
                "malformed, not empty",
            )
        has_real_screens = isinstance(screens_claim, list) and any(
            isinstance(entry, dict) for entry in screens_claim
        )
        if has_real_screens or isinstance(design_fidelity.get("triage"), dict):
            return CheckResult(
                name, False,
                "design_fidelity recorded as skipped, but it also carries "
                "screens or a triage block — a 'skipped' claim its own "
                "record contradicts",
            )
        return CheckResult(
            name, True,
            "design fidelity layer recorded as skipped — nothing to recompute",
            severity=Severity.SKIPPED.value,
        )

    screens = design_fidelity.get("screens")
    usable_screens = [s for s in screens if isinstance(s, dict)] if isinstance(screens, list) else []
    if not isinstance(screens, list) or (not usable_screens and build_screens):
        # Tier-3 CI review (PR #748): a missing/malformed/empty `screens`
        # list — or one holding only junk (non-dict) entries the
        # recomputation below can't use — is not the same as "every screen
        # resolved cleanly" when the build side declares real screens: that
        # combination means the comparison never actually covered any of
        # them, the same "comparison step never ran" gap already caught
        # above for a missing `design_fidelity` block entirely. Silently
        # coercing it to `[]` let a fabricated all-zero triage block sail
        # through without a single screen being checked.
        if build_screens:
            return CheckResult(
                name, False,
                f"design-fidelity-report.json declares {len(build_screens)} "
                f"screen(s), but design_fidelity.screens is missing, "
                f"malformed, empty, or has no usable entries — the "
                f"comparison step never actually covered them",
            )
        screens = []
    else:
        screens = usable_screens

    expected_counts = {key: 0 for key in _TRIAGE_RECORD_KEYS.values()}
    for screen in screens:
        if not isinstance(screen, dict):
            continue
        mockup = screen.get("mockup")
        current_status = screen.get("status")
        build_entry = build_screens.get(mockup) if isinstance(mockup, str) else None
        build_status = build_entry.get("status") if isinstance(build_entry, dict) else None
        category = _categorize_fidelity_screen(build_status, current_status)
        if category is None:
            continue
        expected_counts[_TRIAGE_RECORD_KEYS[category]] += 1

    recorded_triage = design_fidelity.get("triage")
    if not isinstance(recorded_triage, dict):
        needing_triage = sum(expected_counts[key] for key in _TRIAGE_REQUIRING_KEYS)
        if needing_triage:
            return CheckResult(
                name, False,
                f"recomputation found {needing_triage} screen(s) "
                f"needing triage ({expected_counts}), but no triage block was "
                f"recorded — a needs_review screen with no triage entry is "
                f"exactly the 'regression == never-checked' gap this criterion "
                f"forbids",
            )
        return CheckResult(
            name, True,
            "no triage block recorded, and recomputation finds no screen that "
            "needs one — every screen either passed or improved",
            severity=Severity.SKIPPED.value,
        )

    count_errors = _validate_triage_counts(recorded_triage, expected_counts)
    if count_errors:
        return CheckResult(
            name, False,
            "recorded design_fidelity.triage has unrecognized/malformed "
            "field(s) — " + "; ".join(count_errors),
        )

    mismatches = [
        f"{key}: recorded={recorded_triage.get(key)!r} recomputed={expected_counts[key]}"
        for key in expected_counts
        if recorded_triage.get(key) != expected_counts[key]
    ]
    if mismatches:
        return CheckResult(
            name, False,
            "recorded design_fidelity.triage disagrees with a mechanical "
            "recomputation — " + "; ".join(mismatches) +
            " (if both design-fidelity-report.json and shipwright_test_results.json "
            "are from different runs, regenerate one before trusting this failure)",
        )
    return CheckResult(name, True, f"triage counts match: {expected_counts}")


__all__ = [
    "check_design_fidelity_triage_matches_recomputation",
]
