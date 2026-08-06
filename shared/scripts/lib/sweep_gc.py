"""GC delivered-membership logic for the D2 outbox sweep (serialization-drift-immune).

Split from :mod:`lib.sweep_outbox` (D2 review cascade — FIX B, doubt-1) so the
sweep orchestrator stays under the 300-LOC guideline and the GC membership rule
is unit-testable in isolation. :func:`delivered_membership` reads ``origin``'s blob
(the one git call here); the membership RULE below it stays pure.

The GC drops an outbox line ONLY once it is reachable from ``origin/<default>``.
Historically that was a raw stripped-text comparison. FIX B replaced it, for
``append`` lines only, with a match on the semantic ``id``.

**That id-only rule was a defect** (audit findings 14 + 27, fixed
iterate-2026-08-05-it1-audit-remainder). It asked two different questions:

* an ``append`` was delivered iff its *id* was in origin — **content ignored**. A
  producer that re-appends an UPDATED version of an existing finding therefore had
  that update GC'd from the outbox while only the OLD version was in origin. The
  outbox is gitignored, so the new content then existed nowhere (F14). Not
  hypothetical: the tracked log carries a record whose ``ts`` ends ``+00:00``,
  which ``triage._now_z()`` can never emit — a foreign producer really does
  re-serialize same-id records.
* everything else was delivered iff its *raw text* was in origin, so any
  re-serialization made a status line permanently un-GC-able and the gitignored
  buffer grew with no bound and no signal (F27).

Both are now one rule: **canonical-form membership**. A line that parses to a
``dict`` is delivered iff its canonical form is among origin's canonical forms;
anything else keeps raw-text membership. This preserves what FIX B was actually
for — immunity to key-order / whitespace re-serialization — while making a
CONTENT difference visible again.

**Accepted limitation, card ``trg-…`` (P2.19g).** ``dedup_triage_lines`` keeps
only the LAST append per id at materialize, so an earlier same-id append never
reaches a branch and therefore never origin — and under this rule its canonical form
is never in origin either, so it stays in the gitignored buffer indefinitely. The
old id-only rule drained it. A drainage hatch for exactly that class was built,
reviewed three times and DELETED: it was the only path in this module able to delete
the LAST copy of a record (dedup having kept it off the branch by definition), its
correctness was an agreement between this module and ``churn_merge`` that no test
could hold, and two of three attempts leaked in the DROP direction. Measured on the
real 1457-line log: ZERO superseded appends. Retaining a line the old rule dropped
is strictly the fail-safe direction, so the accumulation is accepted and recorded
rather than traded for a deletion authority worth nothing today.

Fail-safety is unchanged and is the invariant to protect: a non-delivered line
always survives, a missing ``origin`` ref yields empty sets so nothing is GC'd,
and every input that cannot be canonicalized degrades to text membership rather
than raising — this code runs inside the sweep's canonical lock and on the
``setup_iterate_worktree`` step-5 path, where an escaping exception aborts setup
after ``git worktree add`` has already succeeded.
"""

from __future__ import annotations

from pathlib import Path

from lib.churn_merge import TRIAGE_LOG
from lib.git_base import run_git_soft
from lib.sweep_canon import canonical_form
from lib.sweep_text import normalized_set


def delivered_membership(
    main_root: Path, default_branch: str,
) -> tuple[set[str], set[str]]:
    """Read ``origin/<default>:<triage>`` and parse it into the
    ``(canonical, text)`` GC anchors. An outbox line is safe to drop only once
    reachable from ``origin``. A non-zero exit yields two EMPTY sets —
    nothing GC'd (fail-safe; a line origin does not provably hold always survives).

    Via :func:`lib.git_base.run_git_soft`, so a TIMEOUT lands in that same fail-safe
    branch instead of raising. This runs inside the sweep's canonical triage lock and
    on the ``setup_iterate_worktree`` step-5 path, where an escaping ``TimeoutExpired``
    aborts setup after ``git worktree add`` has already succeeded. "Could not read
    origin" and "origin has nothing" call for the identical, already-safe answer:
    drop nothing.
    """
    # KNOWN LIMITATION, deferred by decision to card ``trg-94d3cb73`` (P2.19f):
    # ``run_git_soft`` decodes with ``errors="replace"`` while the outbox is read with
    # ``errors="surrogateescape"``, so a line carrying a non-UTF-8 byte yields a
    # DIFFERENT string on each side and matches on neither path — it is retained
    # forever. Direction is retention, never loss. Not fixed here because both
    # remedies are disproportionate: changing ``run_git`` touches its 133 call sites,
    # and bypassing it locally would discard the ``TimeoutExpired`` handling that
    # audit findings 1 and 7 installed for this exact path.
    proc = run_git_soft(["show", f"origin/{default_branch}:{TRIAGE_LOG}"], cwd=main_root)
    if proc.returncode != 0:
        return set(), set()
    return parse_delivered(normalized_set(proc.stdout))


def parse_delivered(normalized_lines: set[str]) -> tuple[set[str], set[str]]:
    """Split origin's stripped/CRLF-absorbed lines into ``(canonical, text)``.

    * ``canonical`` — the canonical form of every line that IS a JSON object,
      whatever its ``event``. An outbox line is delivered iff its own canonical
      form is in here, so a re-serialization matches but a content change does not.
    * ``text`` — the stripped raw line of everything without a canonical form
      (unparseable, bare scalar, duplicate keys, any float). Exact text membership.

    No id set is returned. Id-alone matching IS the F14 defect, and with the
    supersession hatch deleted nothing needs one — so the type system no longer
    offers a future caller the thing that caused the bug.
    """
    canonical: set[str] = set()
    text: set[str] = set()
    for stripped in normalized_lines:
        form = canonical_form(stripped)
        if form is None:
            text.add(stripped)
        else:
            canonical.add(form)
    return canonical, text


def partition_outbox(
    current_lines: list[str],
    membership: tuple[set[str], set[str]],
    quarantined_text: set[str],
) -> tuple[list[str], int]:
    """Split the re-read outbox into ``(survivors, gc_dropped)``.

    Lives here rather than inline in the sweep so the ENTIRE drop decision — the
    membership rule and the quarantine skip — is readable in one module. ``current_lines`` is the sweep's RE-READ of the outbox
    (never the pre-commit read: an append landing in that window must survive), and
    quarantined candidates are still on disk, so skipping them here is what removes
    them.
    """
    delivered_canonical, delivered_text = membership
    survivors: list[str] = []
    gc_dropped = 0
    for line in current_lines:
        stripped = line.strip()
        if not stripped or stripped in quarantined_text:
            continue
        if is_delivered(stripped, delivered_canonical=delivered_canonical,
                        delivered_text=delivered_text):
            gc_dropped += 1
            continue
        survivors.append(line)
    return survivors, gc_dropped


def is_delivered(
    stripped_line: str,
    *,
    delivered_canonical: set[str],
    delivered_text: set[str],
) -> bool:
    """True iff ``stripped_line`` (an outbox line, already stripped/CRLF-absorbed)
    is safe for the GC to drop.

    Delivered iff its canonical form is in ``delivered_canonical``, or — for a line
    with no canonical form — its stripped text is in ``delivered_text``. Anything
    else SURVIVES: a line origin has not provably got is never dropped.

    The two sets are KEYWORD-ONLY on purpose. Parameter 2 used to be an id set and
    now carries canonical forms; a caller written against the old contract would pass
    ids positionally, get no error, and silently evaluate every line as not-delivered.
    That direction is fail-safe, but silence is the failure mode this whole change
    exists to end — and ``shared/`` does not auto-sync to the plugin cache Claude Code
    runs from, so an old caller really can coexist with a new callee for a while.
    Keyword-only makes such a call fail loudly instead (Stage-3 review).
    """
    form = canonical_form(stripped_line)
    if form is None:
        return stripped_line in delivered_text
    return form in delivered_canonical
