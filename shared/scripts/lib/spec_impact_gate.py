"""The spec-impact gate: every iterate says what it did to the requirements.

A feature, a change and a **fix** each record either the FRs they touched
(``affected_frs`` / ``new_frs``) or ``spec_impact: none``. ``none`` carries two
answers: a one-line justification (``spec_impact_justification``, or the
FR-gate's ``none_reason``, which F11's ``check_spec_impact_recorded`` already
reads as the same field) and a ``spec_impact_reason_code`` from the closed
``spec_impact_none`` family in :mod:`lib.reason_codes`. Free text alone can say
anything, so a report could never count or refuse it.

Fixes used to be exempt ("a bug fix need not touch the spec"). That exemption is
gone: a fix that only restores what the spec already says records ``none`` with
``restores-specified-behavior`` - one line, and the claim is now on record.

Moved out of ``record_event.py`` (over its size cap, ADR-111) so that
:func:`lib.fr_gates.run_fr_gates` can run it. Both write paths call that one
entry point, so the gate now runs at F5b (``finalize_iterate``) as well as at
the CLI; before, it ran at the CLI only and F5b skipped it.

Every recorded ``none`` is answered, with or without FRs alongside it (F11
already demands the justification for any ``none``). Intent-less events are not
asked to classify (build-shaped and pre-gate events still parse), but a
``none`` they DO record is answered too.
"""

from __future__ import annotations

from lib.fr_classification import NONE_REASON_MAX_LEN, is_valid_none_reason
from lib.reason_codes import reason_code_error

__all__ = ["SPEC_IMPACT_INTENTS", "SPEC_IMPACT_NONE_FAMILY", "spec_impact_gate_error"]

#: Intents that must classify their spec impact. ``bug`` is included on purpose.
SPEC_IMPACT_INTENTS = frozenset({"feature", "change", "bug"})

#: The closed family a ``spec_impact: none`` reason code is drawn from.
SPEC_IMPACT_NONE_FAMILY = "spec_impact_none"


def _none_error(event: dict) -> dict | None:
    justification = event.get("spec_impact_justification")
    if justification is None:
        justification = event.get("none_reason")
    if not is_valid_none_reason(justification):
        return {
            "error": "spec_impact_none_requires_justification",
            "detail": (
                "An iterate recording --spec-impact none must also pass "
                "--spec-impact-justification (F5b: spec_impact_justification) - "
                f"one line of text (max {NONE_REASON_MAX_LEN} chars, no line breaks) "
                "saying why no requirement changed."
            ),
        }
    problem = reason_code_error(
        SPEC_IMPACT_NONE_FAMILY, event.get("spec_impact_reason_code"),
        where="spec_impact_reason_code",
    )
    if problem:
        return {
            "error": "spec_impact_none_requires_reason_code",
            "detail": (
                f"{problem}. spec_impact none needs a closed-vocabulary code "
                "(--spec-impact-reason-code / F5b spec_impact_reason_code). A fix that "
                "only restores what the spec already states uses restores-specified-behavior."
            ),
        }
    return None


def spec_impact_gate_error(event) -> dict | None:
    """Error dict when an iterate event leaves its spec impact unanswered, else ``None``."""
    if not isinstance(event, dict):
        return None
    if event.get("type") != "work_completed" or event.get("source") != "iterate":
        return None
    if str(event.get("spec_impact", "")).strip().lower() == "none":
        return _none_error(event)
    if str(event.get("intent", "")).strip().lower() not in SPEC_IMPACT_INTENTS:
        return None
    if event.get("affected_frs") or event.get("new_frs"):
        return None
    return {
        "error": "spec_impact_unclassified",
        "detail": (
            "A feature/change/bug iterate work_completed event must record "
            "--affected-frs or --new-frs (the FRs it added, modified or restored), "
            "or --spec-impact none with a --spec-impact-justification and a "
            "--spec-impact-reason-code. Fixes are not exempt. "
            "See SKILL.md Step 2 (ADD/MODIFY/REMOVE/NONE)."
        ),
    }
