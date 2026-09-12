"""Pure triage-categorization logic for the design-fidelity gate (FR-01.06
#7, sub-iterate ``e3-checks-test-security``). Split out of
``_test_gate_fidelity.py`` when that file crossed 300 lines a second time
(round 6, Stage-2 code-reviewer re-review of PR #748).
"""

from __future__ import annotations

# step-3.7-design-fidelity.md's own category table, keyed by (build_status,
# current_status). `None` means the pair is out of the table's scope — an
# `error` current status (no mockup/implementation file resolved) is never
# asked to be triaged by the skill.
TRIAGE_RECORD_KEYS = {
    "resolved": "resolved",
    "regression": "regressions",
    "persistent_failure": "persistent_failures",
    "unchecked": "unchecked",
}

# The categories whose PRESENCE obliges a recorded triage block. `resolved`
# is deliberately absent: a screen that went partial -> pass got BETTER, and
# a run whose only fidelity movement is improvement owes no triage entry.
# All four keys still take part in the count comparison further down -- a
# triage block that IS recorded must get `resolved` right too.
TRIAGE_REQUIRING_KEYS = ("regressions", "persistent_failures", "unchecked")


def validate_triage_counts(recorded_triage: dict, keys) -> list[str]:
    """Every recorded ``design_fidelity.triage`` count must be a non-boolean,
    non-negative integer before it is compared against a recomputed count —
    ``bool`` is an ``int`` subclass in Python, so a recorded ``true``/``false``
    would otherwise compare equal to ``1``/``0`` and silently pass a
    malformed triage block (Tier-3 CI review, round 3, PR #748). Returns one
    diagnostic string per malformed field, empty when all are valid.
    """
    return [
        f"{key}={recorded_triage.get(key)!r} is not a non-negative integer"
        for key in keys
        if isinstance(recorded_triage.get(key), bool)
        or not isinstance(recorded_triage.get(key), int)
        or recorded_triage.get(key) < 0
    ]


def categorize_fidelity_screen(build_status: object, current_status: object) -> str | None:
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
