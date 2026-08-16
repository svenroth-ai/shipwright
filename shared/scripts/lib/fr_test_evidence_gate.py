"""A behaviour-affecting, FR-declaring event must carry test evidence OR
state why it cannot. Mirrors the ``change_type``+``none_reason`` shape BP-1's
classification gate (:mod:`lib.fr_gates`) already uses for the no-FR case.

MEASURED 2026-08-16: 48 of 119 recorded ``work_completed`` events that
declare FRs carry no ``tests.total`` at all — ``record_event.build_event``
builds the ``tests`` block purely from ``--tests-*`` CLI args, so a caller
that passes none gets no block and nothing objects. An event can then
declare ``spec_impact: modify`` plus ``affected_frs`` with zero test
evidence, and ``_reconciliation.compute_reconciliation`` marks those FRs
behaviour-touched with nothing verifying them — permanently, since
reconciliation keys on touched-without-re-verify and never on age.

Extracted into its own module rather than grown onto ``lib.fr_gates``: that
module is already at 286 of its 300-LOC guideline on its two existing gates
(S0 existence + BP-1 classification), and appending this cluster would cross
it. The precedent it set for itself (splitting cohesive clusters into their
own module rather than growing an existing one) applies here too.
:func:`lib.fr_gates.run_fr_gates` imports and wires this in as the third
(last) of its three gates.

Origin: iterate-2026-08-16-fr-gate-test-evidence.
"""

from __future__ import annotations

from lib.fr_classification import (
    NONE_REASON_MAX_LEN as _NONE_REASON_MAX_LEN,
    is_behavior_affecting as _is_behavior_affecting,
    is_non_empty_fr_list as _is_non_empty_fr_list,
    is_valid_none_reason as _is_valid_none_reason,
)

#: `no_tests_reason` is the same one-line-justification shape as `none_reason`
#: — reusing the validator/cap keeps the two disciplines from drifting apart
#: rather than growing a second vocabulary.
_is_valid_no_tests_reason = _is_valid_none_reason


def missing_test_evidence_error(event) -> dict | None:
    """Scope, deliberately narrow: only a **behaviour-affecting**
    (:func:`_is_behavior_affecting`) event that also **declares FR(s)**
    is gated — PLUS any event that **mints** an FR (non-empty ``new_frs``),
    regardless of its ``spec_impact`` label, since minting a requirement is
    always an "add" and a ``spec_impact: none`` alongside it would be
    self-contradictory. A docs-only / behaviour-preserving iterate that only
    *references* existing FRs (``affected_frs``, no ``new_frs``) is never
    touched by this rule — it stays a legitimate no-test case, same as
    before. An FR-less event is left to the classification gate
    (``fr_gates.fr_or_change_type_gate_error``), which already refuses it on
    different grounds; refusing it here too would just produce a second,
    redundant error for the same event.

    "Test evidence" means a ``tests`` block present as a dict with an int
    ``total`` key ``> 0`` — matching every read-side consumer of this same
    field (``_reconciliation.compute_reconciliation``,
    ``_traceability.iterate_test_coverage``, the RTM generator,
    ``iterate_tests_block.derive_tests_block``, which refuses to write
    ``total <= 0`` for exactly this reason: "zero tests is not evidence —
    writing it would look like a claim"). A `tests` value that is present
    but not a dict, missing ``total``, or carrying ``total <= 0`` (including
    an explicit ``0``) is treated as no evidence (falls through to requiring
    `no_tests_reason`) — a caller that ran zero selected tests has evidence
    of nothing and must say why, exactly like a caller that ran none at all.

    Hard-rejects otherwise (error dict). Scope mirrors
    ``fr_gates.fr_or_change_type_gate_error``: runs at the CLI boundary
    (``record_event.main``) and inside ``finalize_iterate._record_event``
    via ``fr_gates.run_fr_gates``, so the two write paths cannot drift
    (ADR-059 parity). Build events (``source != "iterate"``) and
    non-work_completed events bypass entirely, same as the classification
    gate.
    """
    if not isinstance(event, dict):
        return None
    if event.get("type") != "work_completed":
        return None
    if event.get("source") != "iterate":
        return None
    # `new_frs` mints a requirement that did not exist before — that is always
    # an "add", so it needs evidence regardless of the event's own `spec_impact`
    # label (doubt-review D3-1: `spec_impact: none` + `new_frs` would otherwise
    # slip an unevidenced brand-new FR through the bypass meant for referencing
    # existing ones without touching them — self-contradictory and undetected).
    mints_frs = _is_non_empty_fr_list(event.get("new_frs"))
    if not mints_frs and not _is_behavior_affecting(event.get("spec_impact")):
        return None

    has_frs = mints_frs or _is_non_empty_fr_list(event.get("affected_frs"))
    if not has_frs:
        return None

    tests = event.get("tests")
    total = tests.get("total") if isinstance(tests, dict) else None
    has_test_evidence = isinstance(total, int) and not isinstance(total, bool) and total > 0
    if has_test_evidence:
        return None

    if _is_valid_no_tests_reason(event.get("no_tests_reason")):
        return None

    return {
        "error": "fr_gate_missing_test_evidence",
        "detail": (
            f"spec_impact={event.get('spec_impact')!r} is behavior-affecting "
            "and names FR(s) but the event carries no tests.total > 0 and no "
            "no_tests_reason. A behavior-affecting FR-declaring change must "
            "record test evidence (--tests-total at the CLI, or a tests.total "
            "in --event-extras-json at F5b) OR state why it cannot: "
            "--no-tests-reason at the CLI, or a no_tests_reason key in "
            "--event-extras-json at F5b — either way a one-line reason, "
            f"max {_NONE_REASON_MAX_LEN} chars, no newlines. A docs-only "
            "or behaviour-preserving change that only REFERENCES existing "
            "FRs (spec_impact none, no new_frs) is never gated by this "
            "rule — minting a new FR (new_frs) always needs evidence, "
            "regardless of spec_impact. See references/F7.md (CLI) or "
            "F5b.md (finalize)."
        ),
    }
