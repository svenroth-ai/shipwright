"""Pure line-shape predicates for the main-tree drift adoption.

A NEUTRAL LEAF, the same reasoning as :mod:`lib.sweep_text` / :mod:`lib.jsonl_records`
/ :mod:`lib.sweep_gc`: these are stdlib-only, git-free and I/O-free, they are what
:mod:`lib.sweep_drift`'s refusal rules are expressed in, and splitting them keeps that
module under the 300-LOC guideline it shares with the rest of the sweep family.

:mod:`lib.sweep_drift` re-exports :func:`append_ids_of`, so existing importers keep
resolving.
"""

from __future__ import annotations

import json

from lib.jsonl_records import split_records
from lib.triage_gc_publish import DIVERGENCE_CONSEQUENCE

__all__ = ["append_ids_of"]


#: Producer event kinds a drift line may carry. Anything else is not a line this module
#: is willing to move (and therefore not one it is willing to delete from the log either).
_EVENTS = frozenset({"append", "status"})


def append_ids_of(lines: list[str]) -> frozenset[str]:
    """Ids of every well-formed ``append`` event in ``lines``, recovering record boundaries.

    Only valid appends enter the universe (external review): a fragment that does not
    decode, a non-object, or a non-``str`` id contributes nothing — none of those may
    protect a status from the orphan check.

    RECORD-BOUNDARY RECOVERY (iterate-2026-08-06-triage-validate-deadends, Stage-2 code
    review finding 1). This is the PROTECTION universe: an id present here stops a
    ``status`` being read as an orphan and quarantined away. The per-physical-line
    ``json.loads`` it used to do therefore failed in the DESTROYING direction — an append
    committed on local main inside a line glued by an unterminated write vanished from the
    universe, so the operator's dismiss for it became an unprotected orphan, was
    quarantined, and the item resurrected once main reached origin. That is the
    composition of the two defects this run fixes (a glued line × an append only local
    main has), and the validator recovering such a line while this did not is exactly the
    disagreement the run exists to remove.

    Widening this universe is monotonically SAFE: an extra id can only PREVENT a
    quarantine, never cause one. Adoption stays deliberately line-granular and
    conservative — ``_is_producer_event`` still refuses a glued line, so the sweep
    refuses to MOVE one rather than re-serializing it.
    """
    ids: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        records, _remainder = split_records(stripped)
        for obj in records:
            iid = obj.get("id")
            if obj.get("event") == "append" and isinstance(iid, str):
                ids.add(iid)
    return frozenset(ids)


def _parsed(line: str) -> dict | None:
    if not line.strip():
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _looks_like_producer_record(obj: object) -> bool:
    """Shaped like a producer event (append / status with a str id) — the ONE
    definition :func:`_is_producer_event` and :func:`_is_glued_producer_line` both
    defer to (external review: two independent copies of this shape would drift the
    moment ``_EVENTS`` or the id contract changes). Also usable as :func:`split_records`'s
    ``is_record`` predicate — same shape, either source.

    Deliberately looser than :func:`lib.triage_integrity.is_triage_record`, which requires
    every key a real writer always emits per event kind — hardened against a forged-record
    shape that satisfied only ``event``+``id`` (that predicate WRITES recovered objects back
    to disk during repair, so under-rejecting there is an injection risk). Nothing here is
    ever written back: this module only picks the wording of a refusal message, so the
    looser, pre-existing shape ``_is_producer_event`` already used is kept rather than
    swapped (Stage-2 code review finding 1)."""
    return isinstance(obj, dict) and obj.get("event") in _EVENTS and isinstance(obj.get("id"), str)


def _is_producer_event(line: str) -> bool:
    """True iff ``line`` is a well-formed triage producer event — the only shape
    adoption is willing to move."""
    return _looks_like_producer_record(_parsed(line))


def _is_glued_producer_line(line: str) -> bool:
    """True iff ``line`` fails :func:`_is_producer_event` on its own, but a well-formed
    producer record can be recovered from it via record-boundary recovery
    (iterate-2026-08-07-triage-adopt-glued-refusal, P2.19h — residual of P2.19b/AC14).

    Recognising this does NOT license adoption: :func:`lib.sweep_drift.plan_main_tracked_drift`
    moves a drift line onto the outbox VERBATIM, one physical line at a time, never
    re-serializing it. Moving a glued line as-is would carry the glue straight into the
    outbox rather than un-corrupting it — the same reasoning AC14 already gave for why
    ``_is_producer_event`` refuses to move one. This predicate only lets the CALLER tell
    that known, self-healing shape apart from genuine corruption, so the refusal it
    produces can name ``triage_repair.py`` — the tool that splits such a line on disk —
    instead of reading like unexplained data loss.

    UNLIKE :func:`append_ids_of`, this passes ``is_record`` to :func:`split_records`, so
    backward resync is available: :mod:`lib.jsonl_records` names a damaged PREFIX (a
    truncated predecessor write appended onto) the PRIMARY corruption shape, not only the
    two-complete-records-glued case ``append_ids_of`` was fixed for. ``append_ids_of``
    stays untouched — widening the read-only PROTECTION universe is a separate,
    already-shipped decision (P2.19b/AC14) — but this predicate answers a narrower
    question (does the caller's refusal reason for THIS line owe an explanation?). A
    wrong ``True`` only costs message precision (adoption still refuses either way); a
    wrong ``False`` costs the escape hatch. Bounded by
    :data:`lib.jsonl_records._MAX_RESYNC_ATTEMPTS`, same as every other resync caller —
    and that bound is exactly why coverage here is not total: resync requires EVERY
    object in a candidate run to satisfy this predicate's shape, so a truncated prefix
    glued to a valid record AND then unrelated non-record garbage, or a prefix carrying
    more than the resync attempt cap worth of open braces, still falls back to
    ``main_tracked_unparseable`` (doubt review, low). That degrades message precision
    only — the hint is folded into BOTH reason codes, so the escape hatch survives even
    the misclassified case.

    "Glued" here means only "a producer record is recoverable somewhere on this
    line" — it does NOT mean the rest of the line is otherwise benign. A valid
    record followed by unrelated garbage also returns ``True`` (external review):
    that garbage is exactly what ``triage_repair.py`` quarantines, so the refusal
    is still an accurate pointer at the remedy, not a promise the whole line is
    clean."""
    stripped = line.strip()
    if not stripped or _is_producer_event(stripped):
        return False
    records, _remainder = split_records(stripped, is_record=_looks_like_producer_record)
    return any(_looks_like_producer_record(obj) for obj in records)


def _is_header(line: str) -> bool:
    obj = _parsed(line)
    return bool(obj) and obj.get("schema") == "triage" and "v" in obj


#: `<root>` (never `.`); `--writers-quiesced` literal since `triage_repair.main` exits 2 without it.
#: The commit reminder is load-bearing, not decoration (doubt review, medium): `triage_repair`
#: rewrites the tracked log in place and never commits, so an operator who applies it and stops
#: has traded one refusal for `main_tracked_diverged` on every subsequent sweep — the exact
#: divergence :data:`lib.triage_gc_publish.DIVERGENCE_CONSEQUENCE` already names for the sibling
#: `triage_gc --apply` tool, quoted rather than restated so the two remedies cannot drift apart.
_REPAIR_HINT = ("see `uv run shared/scripts/tools/triage_repair.py --project-root <root>` "
                "(add --apply --writers-quiesced once no other writer is live), then commit "
                "the repaired log on main — until you do, " + DIVERGENCE_CONSEQUENCE)


def _bad_drift_reason(bad: int, line: str) -> str:
    """Refusal for :func:`lib.sweep_drift.plan_main_tracked_drift`'s drift line ``bad``
    (1-indexed): glued (the AC14 shape — iterate-2026-08-06-triage-validate-deadends) gets
    a distinct code from genuine corruption; both name the repair tool."""
    if _is_glued_producer_line(line):
        code = "main_tracked_glued_line"
        what = "holds a recognisable triage producer event glued to other content on one line"
    else:
        code, what = "main_tracked_unparseable", "is not a triage producer event"
    return f"{code}: drift line {bad} {what}; {_REPAIR_HINT}"
