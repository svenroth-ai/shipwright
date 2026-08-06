"""Triage-log validation + failure classification (pure; no git / no IO).

Extracted from :mod:`lib.churn_merge` (iterate-2026-06-30-sweep-outbox-quarantine-orphans)
so the triage validator stays a small, single-source cluster and ``churn_merge``
stays under the 300-LOC guideline. ``churn_merge`` re-exports these names, so the
historical ``from lib.churn_merge import validate_triage_text`` import path is
unchanged.

:func:`classify_triage_text` is the single source of truth; :func:`validate_triage_text`
is a thin projection that returns only the string-error list (its historical API).
The added structure lets the outbox sweep distinguish the *recoverable* orphan-status
class (a ``status`` whose id has no ``append`` anywhere — the reader silently drops it)
from genuine corruption (bad/missing header, duplicate append, invalid JSON, empty log).

RECORD-BOUNDARY RECOVERY (iterate-2026-08-06-triage-validate-deadends)
----------------------------------------------------------------------
This module parses with :func:`lib.jsonl_records.split_records`, NOT ``json.loads``
per physical line. The log's one-record-per-line invariant is not enforced at the
append boundary, so an interrupted or external write leaves two records glued onto
one line — the documented motivating failure for ``lib.jsonl_records``. The reader
recovers such a line and the event-log twin
:func:`lib.churn_merge.validate_events_text` was converted in
iterate-2026-07-20; this validator was not. The gap was not cosmetic: one glued
line read as ``not valid JSON``, the sweep's ``decide`` returned ``block``, and
triage delivery stopped permanently — in that run and every future one — while
``read_all_items`` recovered the same bytes cleanly, so the board showed the item
as applied and nothing surfaced the stall (trg-b854805c, finding 15).

Two consequences are deliberate:

* A **fully recoverable** concatenation is a union artefact and raises nothing.
* A **bare scalar** line (valid JSON, not an object) is a fragment per
  ``split_records``' contract, so it is now reported where it previously passed
  in silence. No reader can use it, and the message names the repair tool.

Every unrecoverable-fragment message names :mod:`tools.triage_repair` — an
operator told the log is corrupt must also be told what fixes it.
"""

from __future__ import annotations

from dataclasses import dataclass

from lib.jsonl_records import split_records

#: Appended to every unrecoverable-fragment error. STATIC by construction: no log
#: content, record id or path is ever interpolated into operator-facing remediation
#: text (external plan review, r1/r2/r3 openai #6).
_REPAIR_HINT = (
    "run `uv run shared/scripts/tools/triage_repair.py --project-root <root>` to "
    "quarantine the fragment and recover the rest"
)


@dataclass(frozen=True)
class TriageValidation:
    """Structured result of :func:`classify_triage_text`.

    ``errors`` — the full string-error list (identical to the historical
    :func:`validate_triage_text` output, same order). ``orphan_status_ids`` — ids
    whose ONLY defect is a ``status`` event with no ``append`` anywhere (the
    recoverable class the outbox sweep can quarantine). ``has_non_orphan_error`` —
    True if any error OUTSIDE the two recoverable classes exists (bad/missing
    header, duplicate append, unrecoverable fragment, empty log); genuine
    corruption a caller must treat as fatal.

    ``unidentified_status`` — True when at least one ``status`` event has no
    ``append`` anywhere AND its id is missing or not a ``str``. Its own class,
    because it fits neither of the others and the gap between them was a dead
    end: the error was recorded but the id could not enter ``orphan_status_ids``,
    so ``decide`` blocked on a line the quarantine could not select (no id) and
    the repair could not fix (the JSON is valid) — trg-b854805c, finding 18.
    Such a record is inert to every reader: ``triage.read_all_items`` pass 2
    skips a status whose id is not a ``str``, which is what licenses the sweep to
    quarantine it rather than hold it — nothing observable is destroyed.

    New fields are TRAILING and defaulted so the historical positional
    construction of this re-exported dataclass keeps working (external plan
    review, r3 openai #3).
    """

    errors: list[str]
    orphan_status_ids: frozenset[str]
    has_non_orphan_error: bool
    unidentified_status: bool = False


def classify_triage_text(text: str) -> TriageValidation:
    """Validate the triage log AND classify its failures (orphan-status vs other).

    Checks: (a) the first RECORD is the ``{"schema":"triage",...}`` header;
    (b) every non-blank line decodes as a sequence of one or more JSON OBJECTS —
    a recoverable concatenation is NOT an error, only an unrecoverable remainder
    is; (c) no duplicate ``append`` for one id; (d) no ``status`` event whose id
    has no ``append`` anywhere.

    Check (a) reads the first *record*, not the first *line*: a glued
    ``header + append`` line has a perfectly good header on it, and the pre-fix
    code consumed the whole line as "the header" and never saw what rode along.
    """
    errors: list[str] = []
    orphan_ids: set[str] = set()
    header_seen = False
    has_other = False
    unidentified = False
    append_ids: set[str] = set()
    status_ids: list[tuple[int, object]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        # Record-boundary recovery via the shared SSoT, mirroring the event-log
        # twin ``validate_events_text``. Stripping is for PARSING only — this
        # function judges text and never persists it, so no caller's bytes,
        # dedup identity or EOL style is affected.
        records, remainder = split_records(stripped)
        for obj in records:
            if not header_seen:
                header_seen = True
                if not (obj.get("schema") == "triage" and "v" in obj):
                    errors.append(
                        f"line {n}: first non-blank line is not the triage header "
                        '({"v":...,"schema":"triage",...}) — the merge reordered or dropped it'
                    )
                    has_other = True
                # The header is not an event either way; whatever follows it on
                # this same physical line still is.
                continue
            event, iid = obj.get("event"), obj.get("id")
            if event == "append":
                # ONLY ``str`` ids participate in identity — the same rule the
                # reader (``read_all_items`` skips a non-str id in BOTH passes)
                # and the dedup (``dedup_triage_lines._append_id`` returns None
                # for one) already follow. Three agreeing is the point: a non-str
                # id is inert everywhere rather than inert in two places and
                # load-bearing in the third. It also makes this loop total —
                # ``append_ids.add(iid)`` raised TypeError on an unhashable id
                # such as ``"id": []``, i.e. crashed the sweep from inside its
                # lock — and it retires a fourth dead end of finding 18's family:
                # two non-identical appends sharing a non-str id were reported as
                # a duplicate the dedup will never collapse, so that log could
                # never be delivered again.
                if isinstance(iid, str):
                    if iid in append_ids:
                        errors.append(f"line {n}: duplicate append for id {iid!r} — the merge double-counted an item")
                        has_other = True
                    append_ids.add(iid)
            elif event == "status":
                status_ids.append((n, iid))
        if remainder:
            # Unchanged in kind — genuine corruption still fails closed — but never
            # again without a remedy. A bare scalar reaches here too: valid JSON,
            # wrong shape, unusable by any reader (``split_records`' contract).
            errors.append(
                f"line {n}: not valid JSON (unrecoverable fragment) — union may have "
                f"corrupted a historic line; {_REPAIR_HINT}"
            )
            has_other = True
    # Second pass: status ids are checked against the FULL append set, NOT only
    # appends seen earlier in file order — ``merge=union`` may legitimately
    # interleave lines so a status precedes its append while both are present
    # (order-sensitive validation would false-fail `triage_invalid`). Only a
    # status whose append is absent ANYWHERE is a real merge drop.
    for n, iid in status_ids:
        # ``isinstance`` first: a non-str id can never be in the (str-only)
        # append set, and testing membership with an unhashable id would raise.
        if not isinstance(iid, str) or iid not in append_ids:
            if isinstance(iid, str):
                errors.append(
                    f"line {n}: status for id {iid!r} has no append anywhere — the merge dropped it"
                )
                orphan_ids.add(iid)
            else:
                # NOT "the merge dropped it" — nothing was dropped. The record
                # names no item, so no reader can apply it and no id-keyed
                # remedy can select it. Its own class, its own sentence.
                errors.append(
                    f"line {n}: status event has no usable id ({iid!r}) — no reader can apply it"
                )
                unidentified = True
    if not header_seen:
        errors.append("triage log is empty after merge — the header was dropped")
        has_other = True
    return TriageValidation(
        errors=errors,
        orphan_status_ids=frozenset(orphan_ids),
        has_non_orphan_error=has_other,
        unidentified_status=unidentified,
    )


def validate_triage_text(text: str) -> list[str]:
    """Return a list of error strings (empty = valid) for the triage log.

    Thin projection of :func:`classify_triage_text` — it reports exactly what the
    classifier found, in the same order.

    Its OUTPUT is deliberately not frozen. iterate-2026-08-06-triage-validate-deadends
    moved three shapes across the valid/invalid line, and the callers
    (``reconcile_triage``, ``resolve_churn_conflicts``, ``sweep_outbox``) are affected
    on purpose — a concatenated line used to abort a churn merge and now recovers,
    while a bare scalar and a non-``str``-id record used to pass in silence and are now
    reported. That trade is pinned by ``test_churn_resolver_triage_validation_shift``.
    """
    return list(classify_triage_text(text).errors)
