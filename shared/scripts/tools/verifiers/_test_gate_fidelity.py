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

from ._test_gate_extras import _safe_project_file
from .common import CheckResult, Severity

# step-3.7-design-fidelity.md's own category table, keyed by (build_status,
# current_status). `None` means the pair is out of the table's scope — an
# `error` current status (no mockup/implementation file resolved) is never
# asked to be triaged by the skill.
_TRIAGE_RECORD_KEYS = {
    "resolved": "resolved",
    "regression": "regressions",
    "persistent_failure": "persistent_failures",
    "unchecked": "unchecked",
}


def _categorize_fidelity_screen(build_status: object, current_status: object) -> str | None:
    """Pure function: (build-time status, test-time status) -> triage
    category, or ``None`` when out of the table's scope.

    ``build_status`` is whatever ``design-fidelity-report.json`` recorded for
    this screen (``"full"`` / ``"partial"`` / ``"skipped"``), or ``None`` when
    the screen is absent from that report entirely. A build-time ``"skipped"``
    is folded into ``unchecked`` alongside "absent from the report" — either
    way, build time never actually assessed the screen.
    """
    if current_status == "pass":
        if build_status == "partial":
            return "resolved"
        return None
    if current_status == "needs_review":
        if build_status == "full":
            return "regression"
        if build_status == "partial":
            return "persistent_failure"
        return "unchecked"
    return None


def check_design_fidelity_triage_matches_recomputation(project_root: Path) -> CheckResult:
    """FR-01.06 #7 (mechanisable half): the Resolved/Regression/Persistent
    Failure/Unchecked triage recorded in ``shipwright_test_results.json``'s
    ``design_fidelity.triage`` must match a mechanical recomputation from the
    two files it is derived from.

    SKIPPED when there is nothing to recompute: no build-time
    ``design-fidelity-report.json``, OR one with an empty/absent ``screens``
    dict (no UI screens this project) even if ``design_fidelity`` is also
    absent at test time; OR a recomputation that finds ZERO screens needing
    triage (every screen already passed structurally, so step 3.7 never
    entered the triage branch — a missing ``triage`` block is then correct,
    not a gap).

    Two distinct FAIL cases, both from the same external-review round on
    this sub-iterate's PR: a build report that DOES declare screens combined
    with test-time recording NO ``design_fidelity`` block at all means the
    comparison step never ran — caught before ever reaching the
    recomputation. A ``design_fidelity`` block that IS present but omits
    ``triage`` while the recomputation finds screens that DO need one FAILS
    too — the original ordering skipped this exact case, letting
    "regression" and "never-checked" both escape the gate by simply omitting
    the block.
    """
    name = "design fidelity triage matches a mechanical recomputation"
    report_path = _safe_project_file(project_root, "design-fidelity-report.json")
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
    build_screens = build_report.get("screens") if isinstance(build_report, dict) else None
    if not isinstance(build_screens, dict):
        build_screens = {}

    try:
        recorded = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed shipwright_test_results.json: {exc}")

    design_fidelity = recorded.get("design_fidelity") if isinstance(recorded, dict) else None
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

    screens = design_fidelity.get("screens")
    if not isinstance(screens, list):
        screens = []

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
        if any(expected_counts.values()):
            return CheckResult(
                name, False,
                f"recomputation found {sum(expected_counts.values())} screen(s) "
                f"needing triage ({expected_counts}), but no triage block was "
                f"recorded — a needs_review screen with no triage entry is "
                f"exactly the 'regression == never-checked' gap this criterion "
                f"forbids",
            )
        return CheckResult(
            name, True,
            "no triage block recorded, and recomputation finds no screen that "
            "needs one — every screen already passed structurally",
            severity=Severity.SKIPPED.value,
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
