"""Disposition rules for the triage outbox sweep — what happens to a line it cannot
deliver.

iterate-2026-06-30-sweep-outbox-quarantine-orphans. When the sweep's materialized
log (``worktree-tracked ∪ outbox``) fails validation ONLY because of orphan-status
lines (a ``status`` whose id has no ``append`` anywhere) that originate in the
OUTBOX, those lines are moved to ``.shipwright/triage.outbox.quarantine.jsonl``
instead of hard-blocking the entire sweep — which previously stranded every
legitimate pending append in the buffer.

iterate-2026-08-06-triage-validate-deadends (trg-b854805c) finished that idea. Two
more classes reached ``block`` with no way back, so delivery stopped permanently
while the board — reading through a recovering reader — showed nothing wrong. Each
class now gets a PROPORTIONAL disposition and ``block`` means only "corruption I
must not paper over":

* **hold**       — a ``status`` whose append is in main's tracked log. Not deliverable
                   YET. Kept in the outbox and retried; the rest of the buffer ships.
* **quarantine** — no append anywhere, or no usable id. Not deliverable EVER.
* **block**      — bad/missing header, duplicate append, unrecoverable fragment, empty
                   log, or any defect in the worktree-tracked log the sweep cannot
                   rewrite. Every such message names a reachable remedy.

A bare-scalar line is a fragment (``split_records``' contract) and so newly blocks
where it used to pass in silence; the message names ``triage_repair.py``.

Split from :mod:`lib.sweep_outbox` so both modules stay under the 300-LOC guideline;
the quarantine LOG WRITER was split out again into :mod:`lib.quarantine_log` for the
same reason and is re-exported here, so every historical importer resolves unchanged.
The caller invokes :func:`decide` + :func:`append_quarantine` under the canonical
triage ``_FileLock`` (same critical section as the rest of the sweep).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lib.churn_merge import (
    TriageValidation,
    classify_triage_text,
    dedup_triage_lines,
    validate_triage_text,
)
from lib.jsonl_records import split_records
from lib.quarantine_log import (  # noqa: F401  (re-export surface)
    QUARANTINE_LOG,
    append_quarantine,
    quarantine_path,
)


@dataclass
class QuarantineDecision:
    """Outcome of :func:`decide`.

    ``action`` ∈ {``clean``, ``hold``, ``quarantine``, ``block``}:
      * ``clean``      — the materialized log validates as-is; deliver normally.
      * ``hold``       — nothing to quarantine, but one or more outbox lines are not
        deliverable YET; they stay buffered and the rest is delivered.
      * ``quarantine`` — at least one outbox line is not deliverable EVER; it moves to
        the quarantine log and the rest is delivered.
      * ``block``      — genuine corruption, or a defect in the worktree-tracked log
        the sweep cannot rewrite; ``errors`` carries the validator output.

    ``action`` names the STRONGEST disposition applied and is for reporting. The
    caller drives its mechanics off the LISTS, because the two can co-occur.

    On ``clean`` / ``hold`` / ``quarantine`` the three line lists partition the input
    exactly — ``materialized_outbox + candidates + held_lines == outbox_lines`` as an
    ORDERED MULTISET, so a duplicated buffered record cannot be silently absorbed. On
    ``block`` all three are EMPTY and the invariant does not apply: a caller that read it
    as unconditional and drove a rewrite off ``materialized_outbox`` would empty the
    buffer. Check ``action`` first.

    * ``materialized_outbox`` — folded into ``deduped_text``. A branch-materialization
      input; it must NEVER be written back as the outbox. (It was called
      ``trimmed_outbox`` until iterate-2026-08-06-triage-validate-deadends; the
      name read as "what the outbox becomes", which is precisely how a withheld
      line gets deleted — external plan review, openai r1 #2 / r3 #1.)
    * ``candidates`` — quarantined: appended to the quarantine log and removed from
      the persisted outbox. The ONLY list the quarantine channel removes.
    * ``held_lines`` — withheld from THIS delivery and RETAINED in the outbox, so the
      next sweep retries them. Never removed *because* they are held; the pre-existing GC
      may still drop one if origin has meanwhile delivered it, which is correct — it is no
      longer held in any meaningful sense. Named ``held_lines``, not ``held``, so it
      cannot be confused with the ``SweepResult.held`` COUNT across the module boundary —
      the same reason ``candidates`` becomes ``quarantined`` there.

    ``deduped_text`` is the post-partition, post-dedup materialized log for the branch.

    ``warnings`` is what the dedup reported while materializing — informational, NEVER
    blocking: a benign keep-last collapse still leaves ``clean`` (finding 25).
    """

    action: str
    deduped_text: str = ""
    materialized_outbox: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    held_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _sole_record(line: str) -> dict | None:
    """The ONE record on ``line``, or ``None`` when it does not hold exactly one.

    Parsed with :func:`split_records` — the same parser the classifier uses, so
    selection can never disagree with classification about what a line contains.
    ``None`` covers both "several records glued together" and "a fragment", which
    are the two shapes the sweep cannot disposition per record.

    Stripping is for PARSING ONLY. Every list built from these lines holds the
    ORIGINAL ``line``, so dedup byte-identity and the file's EOL style survive.
    """
    records, remainder = split_records(line.strip())
    if remainder or len(records) != 1:
        return None
    return records[0]


def _materialize(worktree: list[str], outbox: list[str], eol: str) -> tuple[str, list[str]]:
    """Merged log + what the dedup said — returned, not dropped: a record it declined to collapse is what an operator needs told."""
    deduped, warnings = dedup_triage_lines(worktree + outbox)
    return ((eol.join(deduped) + eol) if deduped else ""), warnings


def decide(
    worktree_lines: list[str],
    outbox_lines: list[str],
    eol: str,
    known_append_ids: frozenset[str] = frozenset(),
) -> QuarantineDecision:
    """Classify the materialized log and decide clean / hold / quarantine / block.

    Only OUTBOX-originating lines can be quarantined or held — the sweep cannot rewrite
    the worktree-tracked/origin log. Either disposition is adopted ONLY when removing
    those lines leaves a fully-clean remainder; any residual error → block. That residual
    re-validation, not the partition, is what keeps a tracked-side defect from being
    papered over by its byte-identical twin in the outbox.

    ``known_append_ids`` widens the orphan UNIVERSE beyond ``worktree-tracked ∪ outbox``
    (iterate-2026-07-14-sweep-drift-dismiss-loss). The caller passes the append ids it
    knows from MAIN's tracked log; a ``status`` for one of those has a real append — it
    is NOT an orphan and must never be quarantined, because quarantining it DELETES the
    operator's only dismiss and the item resurrects on the board forever. Such a status
    is HELD (iterate-2026-08-06-triage-validate-deadends): it used to ``block``, and the
    remedy that block named — "deliver main (push / merge origin)" — is unreachable in a
    workflow where main is only fast-forwarded from origin, so the sweep stopped
    permanently and took every unrelated pending append with it, in a gitignored buffer
    one ``git clean -xfd`` from empty. Holding delivers the rest and retries the line on
    the next sweep, which runs off a freshly fetched ``origin/<default>``.
    """
    text, warnings = _materialize(worktree_lines, outbox_lines, eol)
    verdict = classify_triage_text(text)
    if not verdict.errors:
        return QuarantineDecision("clean", deduped_text=text, warnings=warnings, materialized_outbox=list(outbox_lines))

    # Computed BEFORE the corruption return, not inside the partition, so the hint is
    # attached to EVERY block a split would fix (Stage-2 code review, finding 3). The
    # sharpest case takes that early return: a duplicate append hidden inside a glued
    # outbox line reports "the merge double-counted an item" and sends the operator
    # hunting for a duplicate LINE that does not exist, while `triage_repair.py` —
    # which splits exactly that line — is one command away.
    unsplittable = any(_sole_record(line) is None for line in outbox_lines if line.strip())

    # Also computed BEFORE the corruption return (Stage-3 objection 1). These depend only
    # on the verdict, never on partition state, and passing an empty ``protected`` there
    # reproduced the very defect this run exists to remove: corruption ANYWHERE in the log
    # co-occurring with a legitimately protected dismiss ELSEWHERE emitted the validator's
    # raw "no append anywhere — the merge dropped it" with no correction, sending the
    # operator after corruption that is not there.
    protected = verdict.orphan_status_ids & frozenset(known_append_ids)
    orphan_ids = verdict.orphan_status_ids - frozenset(known_append_ids)

    if verdict.has_non_orphan_error:
        # Genuine corruption, decided BEFORE anything is partitioned or written, so no
        # side effect can be half-applied. Nothing was held (the partition never ran), so
        # the note stays on its unconditional wording.
        return QuarantineDecision(
            "block", errors=_block_errors(verdict, protected, frozenset(), unsplittable), warnings=warnings,
        )

    # Partition BY INDEX in one pass: order and duplicate count are preserved exactly.
    # A set-difference would collapse two identical buffered records into one and
    # silently change what is written back (external plan review, r1 openai #5).
    materialized: list[str] = []
    candidates: list[str] = []
    held: list[str] = []
    held_ids: set[str] = set()
    for line in outbox_lines:
        obj = _sole_record(line)
        if obj is None:
            # This physical line does not hold exactly one record, and the outbox is
            # persisted / quarantined / GC'd BY LINE, so no per-record disposition exists.
            # Re-serializing it here is rejected: triage_repair.py documents that it
            # reflows a CRLF log to LF on a merge=union artifact and breaks the
            # byte-identity dedup. Materialize it; any defect it carries is caught by the
            # residual re-validation below.
            materialized.append(line)
            continue
        iid = obj.get("id")
        if obj.get("event") == "status":
            # ``isinstance`` FIRST and the order is load-bearing: an id may be any JSON
            # value, and ``[] in frozenset(...)`` raises TypeError: unhashable. Testing
            # membership first would crash the sweep from inside its own lock — strictly
            # worse than the dead end this function exists to remove.
            if not isinstance(iid, str) or iid in orphan_ids:
                # No usable id at all, or no append anywhere. Un-deliverable forever, and
                # inert to every reader either way — quarantine destroys nothing.
                candidates.append(line)
                continue
            if iid in protected:
                held.append(line)
                held_ids.add(iid)
                continue
        materialized.append(line)

    if not candidates and not held:
        # Nothing in the OUTBOX explains the verdict, so every defect lives in the
        # worktree-tracked log — which the sweep cannot rewrite. Fail closed.
        return QuarantineDecision("block", errors=_block_errors(verdict, protected, frozenset(held_ids), unsplittable), warnings=warnings)

    trimmed_text, _ = _materialize(worktree_lines, materialized, eol)
    if validate_triage_text(trimmed_text):
        # A residual error after the partition — e.g. a byte-identical copy of the same
        # defect in the worktree-tracked log, or a defect inside a glued line. This
        # re-validation, NOT the partition, is what enforces provenance (external plan
        # review, r2 openai #3).
        return QuarantineDecision("block", errors=_block_errors(verdict, protected, frozenset(held_ids), unsplittable), warnings=warnings)
    return QuarantineDecision(
        "quarantine" if candidates else "hold",
        deduped_text=trimmed_text,
        materialized_outbox=materialized,
        candidates=candidates,
        held_lines=held, warnings=warnings,
    )


def _protected_note(iid: str, was_held: bool) -> str:
    """Why a protected id still could not be placed — worded for the case at hand.

    A protected status is NOT "an append the merge dropped": its append exists, in
    main's tracked log, unreachable from this branch. The validator's own line says
    "has no append anywhere", which would send the operator hunting for corruption
    that is not there, so one of these ALWAYS accompanies it.

    Three drafts of this got the CASE wrong before the wording settled, so the rule
    is now: say only what is true on every path. Naming where the status sits was the
    trap — "it is not in the outbox" is false when it was held (Stage-2 finding 2),
    and equally false when its only outbox copy is glued to another record and so was
    never a candidate for holding (Stage-3 objection 2). The head clause holds
    unconditionally; the held clause is the one extra fact always known when true.
    """
    head = (
        f"protected_status_unplaceable: id {iid!r} has an append in main's tracked log that is "
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


def _block_errors(
    verdict: TriageValidation,
    protected: frozenset[str],
    held_ids: frozenset[str],
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
    # status was not placed either way, and the validator's "no append anywhere" line is
    # actively wrong about it. Only the WORDING depends on whether the outbox copy was
    # withheld.
    errors += [_protected_note(iid, iid in held_ids) for iid in sorted(protected)]
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
