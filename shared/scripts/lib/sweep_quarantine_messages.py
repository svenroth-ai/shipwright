"""Operator-facing block-diagnostic and quarantine-log messages for the triage
outbox sweep.

Split out of :mod:`lib.sweep_quarantine` (which crossed the 300-LOC guideline
when AC12's per-kind `protected_amend_unplaceable` token was added in
iterate-2026-08-08-triage-amend-event) so the message-composition helpers live
apart from :func:`lib.sweep_quarantine.decide`'s classification logic.
:mod:`lib.sweep_quarantine` imports :func:`block_errors` directly;
:mod:`lib.sweep_outbox` imports :func:`quarantine_reason` and
:func:`split_candidates_by_kind` directly (Stage-3 doubt review, finding 3 —
before this, every quarantined candidate was logged with the same "status"
wording regardless of its actual event kind).
"""

from __future__ import annotations

import json

from lib.triage_validate import TriageValidation


def protected_note(iid: str, was_held: bool, *, token: str) -> str:
    """Why a protected id still could not be placed — worded for the case at hand.

    A protected status/amend is NOT "an append the merge dropped": its append exists,
    in main's tracked log, unreachable from this branch. The validator's own line says
    "has no append anywhere", which would send the operator hunting for corruption
    that is not there, so one of these ALWAYS accompanies it.

    Three drafts of this got the CASE wrong before the wording settled, so the rule
    is now: say only what is true on every path. Naming where the record sits was the
    trap — "it is not in the outbox" is false when it was held (Stage-2 finding 2),
    and equally false when its only outbox copy is glued to another record and so was
    never a candidate for holding (Stage-3 objection 2). The head clause holds
    unconditionally; the held clause is the one extra fact always known when true.

    ``token`` (iterate-2026-08-08-triage-amend-event, AC12/M5): a
    ``protected_amend_unplaceable`` note for an amend is a NEW, distinct token from
    the pinned ``protected_status_unplaceable`` one — never a rename, never reused
    across kinds. Naming the wrong event kind here is the exact "corruption that is
    not there" misdirection this module was rewritten to prevent, just in a smaller
    form: an operator told their STATUS is protected when it was an AMEND goes
    hunting the wrong event.
    """
    head = (
        f"{token}: id {iid!r} has an append in main's tracked log that is "
        f"not reachable from this branch, so the 'no append anywhere' above is wrong about it. "
        f"Deliver main to origin, then re-run"
    )
    if was_held:
        # The only extra fact worth stating, and the only one we always know.
        return (
            f"{head} — this run withheld its outbox copy; a further copy in the branch's "
            f"tracked log, which the sweep cannot rewrite, is what blocked"
        )
    return head


def block_errors(
    verdict: TriageValidation,
    protected_status: frozenset[str],
    protected_amend: frozenset[str],
    held_status_ids: frozenset[str],
    held_amend_ids: frozenset[str],
    unsplittable: bool,
) -> list[str]:
    """The validator's errors plus whatever remedy this particular block has.

    EVERY ``block`` return comes through here, so the remedies stay in one place.

    Not every block has a tool remedy, and this does not pretend otherwise: a dropped
    header or an emptied log needs a human looking at the repo, and saying "run the
    repair tool" would be worse than saying nothing. What must never happen again is a
    block whose remedy EXISTS and goes unmentioned — the whole defect class this module
    was rewritten for.
    """
    errors = list(verdict.errors)
    # EVERY protected id gets an explanation, held or not — reaching a block means its
    # status/amend was not placed either way, and the validator's "no append anywhere"
    # line is actively wrong about it. The WORDING depends on whether THAT KIND's own
    # outbox copy was withheld — ``held_status_ids``/``held_amend_ids`` are kept apart
    # (Stage-3 doubt review, finding 6) so an id protected via `status` while its only
    # `amend` copy was never a hold candidate at all cannot make the amend note claim
    # a withholding that did not happen. The TOKEN depends on which event kind
    # protected it — an id protected via both kinds (a buffered status AND a buffered
    # amend for the same id) gets both notes, since both statements are independently
    # true.
    errors += [
        protected_note(iid, iid in held_status_ids, token="protected_status_unplaceable")
        for iid in sorted(protected_status)
    ]
    errors += [
        protected_note(iid, iid in held_amend_ids, token="protected_amend_unplaceable")
        for iid in sorted(protected_amend)
    ]
    if unsplittable:
        # Deliberately not "holds more than one record": ``_sole_record`` also returns
        # None for a fragment, and claiming a concatenation the operator cannot find is
        # the same misdirection this function exists to prevent.
        errors.append(
            "unsplittable_outbox_line: an outbox line does not hold exactly one record, so "
            "the sweep cannot dispose of its records separately — run "
            "`uv run shared/scripts/tools/triage_repair.py --project-root <root>` to split "
            "or quarantine it, then re-run"
        )
    return errors


def quarantine_reason(event: str) -> str:
    """The quarantine-log ``reason`` string for an un-deliverable candidate line,
    keyed by its own event kind — never one shared "status" wording applied to
    an amend candidate too (Stage-3 doubt review, finding 3): the quarantine log
    is the only surviving copy of a line just deleted from the gitignored
    outbox, so mislabeling it here is worse than mislabeling a transient
    operator message — there is no second chance to get the kind right.
    """
    if event == "amend":
        return "un-deliverable amend: no append anywhere in the combined triage log, or no usable id"
    return "un-deliverable status: no append anywhere in the combined triage log, or no usable id"


def split_candidates_by_kind(candidates: list[str]) -> tuple[list[str], list[str]]:
    """Partition quarantine ``candidates`` into ``(status_lines, amend_lines)`` so
    the caller can log each with its own kind-correct :func:`quarantine_reason`.

    Every line in ``candidates`` is guaranteed well-formed JSON holding exactly
    one ``status``/``amend`` record — the only shapes :func:`lib.sweep_quarantine.decide`
    ever adds to that list (anything glued or unparseable takes a different
    path) — so a bare ``json.loads`` is safe here without ``split_records``.
    """
    status_lines: list[str] = []
    amend_lines: list[str] = []
    for line in candidates:
        obj = json.loads(line)
        (amend_lines if obj.get("event") == "amend" else status_lines).append(line)
    return status_lines, amend_lines
