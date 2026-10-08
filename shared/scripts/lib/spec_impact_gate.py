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
``none`` they DO record is answered too. So the classify rule is not opt-in,
F5b stamps ``intent`` from the run's own iterate entry
(:func:`stamp_intent_from_history`) before the gates run.

A ``*-only`` code names a label, so next to a no-FR ``change_type`` the two
must agree (``docs-only`` with ``docs`` and so on). ``tests-only``,
``behavior-preserving`` and ``restores-specified-behavior`` name no label.
"""

from __future__ import annotations

from lib.fr_classification import CHANGE_TYPE_VALUES, NONE_REASON_MAX_LEN, is_non_empty_fr_list, is_valid_none_reason
from lib.reason_codes import reason_code_error

__all__ = [
    "LABEL_OF_CODE", "SPEC_IMPACT_INTENTS", "SPEC_IMPACT_NONE_FAMILY",
    "none_record_problem", "spec_impact_gate_error", "stamp_intent_from_history",
]

#: Intents that must classify their spec impact. ``bug`` is included on purpose.
SPEC_IMPACT_INTENTS = frozenset({"feature", "change", "bug"})

#: The closed family a ``spec_impact: none`` reason code is drawn from.
SPEC_IMPACT_NONE_FAMILY = "spec_impact_none"

#: The no-FR ``change_type`` each label-naming code must sit next to (``<label>-only``),
#: keyed off the FR-gate's own enum so the two can never name different labels.
LABEL_OF_CODE = {f"{label}-only": label for label in CHANGE_TYPE_VALUES}


def _justification(event: dict):
    value = event.get("spec_impact_justification")
    return event.get("none_reason") if value is None else value


def _none_error(event: dict) -> dict | None:
    if not is_valid_none_reason(_justification(event)):
        return {
            "error": "spec_impact_none_requires_justification",
            "detail": (
                "An iterate recording --spec-impact none must also pass "
                "--spec-impact-justification (F5b: spec_impact_justification) - "
                f"one line of text (max {NONE_REASON_MAX_LEN} chars, no line breaks) "
                "saying why no requirement changed."
            ),
        }
    code = event.get("spec_impact_reason_code")
    problem = reason_code_error(SPEC_IMPACT_NONE_FAMILY, code, where="spec_impact_reason_code")
    if problem:
        return {
            "error": "spec_impact_none_requires_reason_code",
            "detail": (
                f"{problem}. spec_impact none needs a closed-vocabulary code "
                "(--spec-impact-reason-code / F5b spec_impact_reason_code). A fix that "
                "only restores what the spec already states uses restores-specified-behavior."
            ),
        }
    label, change_type = LABEL_OF_CODE.get(code), event.get("change_type")
    if label and change_type is not None and change_type != label:
        return {
            "error": "spec_impact_reason_code_contradicts_change_type",
            "detail": (
                f"spec_impact_reason_code={code!r} says the change is {label!r}-only, but "
                f"change_type={change_type!r}. Make them agree, or use a code that names "
                "no label (behavior-preserving, restores-specified-behavior, tests-only)."
            ),
        }
    return None


def none_record_problem(event) -> tuple[str, str] | None:
    """F11's reading of a recorded ``none``: ``("error"|"warning", why)`` or ``None``.

    No valid one-line justification is an error. No closed code is only a
    warning: the write-time gate demands one, so its absence means the event was
    written by an older (or stale cached) writer, not that the claim is empty.
    """
    event = event if isinstance(event, dict) else {}
    if not is_valid_none_reason(_justification(event)):
        return "error", ("spec_impact=none recorded WITHOUT a one-line justification - an "
                         "iterate claiming no spec impact must justify it")
    if reason_code_error(SPEC_IMPACT_NONE_FAMILY, event.get("spec_impact_reason_code")):
        return "warning", ("spec_impact=none is justified but carries no closed "
                           "spec_impact_reason_code (written before the code was required, "
                           "or by a stale plugin cache)")
    return None


def stamp_intent_from_history(event, project_root) -> dict | None:
    """F5b: take ``intent`` from the run's iterate entry ``type``; refuse a contradiction.

    Without this, leaving ``intent`` out of the extras skipped the classify rule.
    No entry (or an entry type outside :data:`SPEC_IMPACT_INTENTS`) changes nothing.
    """
    if not isinstance(event, dict) or not event.get("adr_id"):
        return None
    try:
        from lib.iterate_entry import find_entry_by_run_id
        entry = find_entry_by_run_id(project_root, event["adr_id"]) or {}
    except Exception:  # noqa: BLE001 - an unreadable store is F11's finding, not this one's
        return None
    kind = str(entry.get("type") or "").strip().lower()
    if kind not in SPEC_IMPACT_INTENTS:
        return None
    given = str(event.get("intent") or "").strip().lower()
    if not given:
        event["intent"] = kind
        return None
    if given == kind:
        return None
    return {"error": "spec_impact_intent_mismatch", "detail": (
        f"intent={event.get('intent')!r} contradicts this run's iterate entry type {kind!r} "
        f"(.shipwright/agent_docs/iterates/). Pass the entry's type, or omit intent.")}


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
    if is_non_empty_fr_list(event.get("affected_frs")) or is_non_empty_fr_list(event.get("new_frs")):
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
