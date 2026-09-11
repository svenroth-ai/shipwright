"""Sibling-worktree tracked triage logs — a decision recorded elsewhere.

WHY THIS EXISTS (measured 2026-09-06, trg-5e0b9b16 / trg-e85c5c8e)
-------------------------------------------------------------------
A decision (dismiss/promote/park/amend) recorded directly in a campaign or
iterate worktree's TRACKED ``.shipwright/triage.jsonl`` is invisible to any
other tree reading its own store: ``triage.read_all_items`` only ever unions
ITS OWN tracked + outbox files. An item dismissed only in a worktree
therefore read back on ``main`` as still ``triage``, with ``pendingDelivery``
computing ``False`` — a false reassurance, the one direction an advisory
marker must never fail in.

The general statement is broader than the ``sweep`` path that first surfaced
it (campaign 2026-06-08-triage-outbox-delivery / D2): a decision recorded in
ANY tree other than the one being read is invisible to that reader. This
module addresses one direction — **main reads its siblings**; a worktree
reading main's (or a peer's) later decisions stays unaddressed, since the fix
only needed the direction the measured bug was in, and a worktree has no
``.worktrees`` of its own to discover through in the normal layout. It
locates every sibling worktree's tracked log so :mod:`triage` (the board) and
:mod:`lib.triage_delivery` (the pending marker) can fold status/amend events
for ids they already know about into their own view — reported, never
delivered.

BOUNDARY — reported, never delivered
-------------------------------------
A worktree's tracked log IS the truth and is already on disk; nothing here
writes anything. Folding a foreign event into another tree's read does not
satisfy the origin-delivered GC rule (:mod:`lib.triage_delivery` still needs
the event in the reading tree's OWN tracked store, or on ``origin``), must
never cause an outbox line to be dropped, and must never be written into the
reading tree's tracked log. Only a sibling's TRACKED log is read — never its
outbox, that clone's own undecided buffer. Only a MAIN tree reads its
siblings; a linked worktree never does (no ``.worktrees`` of its own in the
normal layout).

**Local-outranks-foreign precedence (fixed 2026-09-10, trg-74ef24ce) lives in
`triage.read_all_items`, not here** — this module hands its caller every
foreign `status`/`amend` record it finds and applies no precedence itself, by
design (see "reported, never delivered" above). `cross_tree_delivery_facts`
below is UNCHANGED by that fix and must stay that way: a sibling's
undelivered decision is still correctly reported as pending even after this
tree's own tracked log has since overridden it — a true statement about
delivery, not a status the board should show.

**No expiry, by design constraint, not oversight** (Stage-3 doubt review,
finding 3). Whether a branch is abandoned vs. still in flight is a question
only ``git`` can answer (is it merged?), and this module never shells out.
A sibling worktree left on disk after its branch is abandoned therefore
reports its decision as pending forever — never silently, never suppressed.
An operator clears it by removing the worktree; no other GC path exists here.

**Foreign corruption is stderr-only, not part of the JSON contract**
(Stage-3 doubt review, finding 4). It goes through the same
``report_corruption`` side channel as this tree's own store, but
``list --json``'s ``corruption`` block is built from ``store_facts``, which
reads only this tree's own tracked + outbox — a decision lost to corruption
in a sibling has only that stderr line as a signal. Accepted gap, not fixed
here, since folding it in would touch the JSON shape itself.

Design constraints
-------------------
* **Discovery is a separate module** (:mod:`lib.triage_cross_tree_discovery`)
  — locating a sibling and naming its branch, no git subprocess, walked fresh
  on every call by design. See that module's docstring.
* **Cache the PARSE, not the discovery walk** (``_CACHE`` below, keyed on
  ``(path, mtime_ns, size)``). Parsing a sibling's full log — some exceeding
  a thousand records with multi-kilobyte fields — is the one genuinely
  expensive part, and this cache amortizes it across the several
  ``read_all_items`` calls one CLI invocation makes. Process-lifetime only,
  by design — a fresh process per invocation means it never amortizes ACROSS
  invocations (a WebUI poll pays the full parse cost every time); fixing
  that would need a persistent cache, out of scope here.
* **Measured, not guessed, fan-out** (Stage-3 doubt review, finding 1). This
  repo carries 84 sibling worktrees, some logs exceeding a thousand records
  with multi-kilobyte fields — not the "~45 small files" first assumed. Only
  ``status``/``amend`` are ever consumed from a foreign log, so
  ``foreign_records_by_branch`` filters to those two kinds before caching
  rather than retaining every ``append``'s full body. A bounded fix (skip a
  known-merged sibling) needs the ``git`` subprocess this module avoids, or a
  persistent cache — a delivery-receipt-shaped mechanism the original spec
  rejected; both out of scope, recorded as a follow-up.
"""

from __future__ import annotations

from pathlib import Path

from .jsonl_records import read_jsonl_records
from .triage_cross_tree_discovery import sibling_worktree_logs
from .triage_delivery import (
    foreign_undelivered_amends_from_records,
    foreign_undelivered_from_records,
)
from .triage_integrity import is_triage_record, report_corruption

__all__ = [
    "cross_tree_delivery_facts",
    "foreign_records_by_branch",
    "foreign_status_and_amend_records",
    "sibling_worktree_logs",
]

_SHIPWRIGHT_DIR = ".shipwright"
_TRIAGE_FILE = "triage.jsonl"
_OUTBOX_FILE = "triage.outbox.jsonl"

#: (path, mtime_ns, size) -> parsed records. Process-lifetime only, by design
#: (see module docstring) — not a correctness risk: a stale hit only ever costs
#: a re-read on the NEXT process, since nothing here is ever the writer.
_CACHE: dict[Path, tuple[tuple[int, int], list[dict]]] = {}


def _cached_records(path: Path, *, keep=None) -> list[dict]:
    """Tolerant read of ``path``, memoized on ``(path, mtime_ns, size)``.

    Mirrors ``triage._iter_raw_lines_at`` (same predicate, same corruption side
    channel) — reimplemented rather than called back into, so this module
    never needs to import :mod:`triage` (that direction is the exact cycle
    ``lib/jsonl_records.py`` documents as this repo's CodeQL cycle origin, per
    :mod:`lib.triage_integrity`'s own docstring).

    **Fingerprint is (mtime_ns, size), not bare ``st_mtime`` (PR #684 review).**
    A float ``st_mtime`` can round, and on some filesystems its resolution is
    coarser than a second, so two rapid appends can share one value — a cache
    keyed on that alone would then serve the first append's content forever.
    ``st_mtime_ns`` (an int) plus ``st_size`` — which strictly grows on every
    write to an append-only log, this cache's only real workload — needs an
    unindexed rewrite reproducing both exactly to collide.

    ``keep``, if given, filters the parsed records BEFORE they enter the
    cache — not after — so a caller that only ever wants a subset (see
    :func:`foreign_records_by_branch`) never pays to retain the rest for the
    process lifetime. Safe by construction, not just convention: a MAIN
    tree's own tracked/outbox files (read unfiltered — they need ``append``
    records too) and a sibling's log (read filtered, exclusively through
    :func:`foreign_records_by_branch`) can never be the SAME path, because a
    root's ``.git`` cannot be both a directory (main) and a file (linked
    worktree, the shape ``_branch_name`` requires) at once.
    """
    try:
        st = path.stat()
    except OSError:
        return []
    fingerprint = (st.st_mtime_ns, st.st_size)
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    result = read_jsonl_records(path, is_record=is_triage_record)
    report_corruption(result.corrupt)
    records = result.records if keep is None else [r for r in result.records if keep(r)]
    _CACHE[path] = (fingerprint, records)
    return records


def _is_status_or_amend(record: dict) -> bool:
    return record.get("event") in ("status", "amend")


def foreign_records_by_branch(project_root: Path | str) -> list[tuple[str, list[dict]]]:
    """``(branch, records)`` for every sibling worktree — status/amend only.

    Never ``append`` (see the module boundary note) — filtered in at the
    cache, not after, since a sibling's tracked log can run to thousands of
    records with multi-kilobyte fields (Stage-3 doubt review, finding 1) and
    nothing downstream ever consumes a foreign append. Kept per-branch (not
    flattened) so a caller attributing a decision to its origin —
    :func:`lib.triage_delivery.foreign_undelivered_from_records` — can tell
    which branch a given deciding event came from.
    """
    return [
        (branch, _cached_records(path, keep=_is_status_or_amend))
        for branch, path in sibling_worktree_logs(project_root)
    ]


def cross_tree_delivery_facts(
    project_root: Path | str, *, applied_statuses, is_valid_amend,
) -> tuple[set[str], set[str], dict[str, str], dict[str, str]]:
    """``(status_ids, amend_ids, status_origin_branches, amend_origin_branches)``
    for decisions this reader can see only on a sibling worktree — the one
    entry point a CLI/board caller needs; this module owns reading its own
    tracked + outbox records too, so the caller passes nothing but the
    applied-statuses vocabulary and amend validator it already has.

    The two id sets are meant to fold into that caller's existing
    outbox-only ``undelivered*`` sets (a decision pending for either reason
    reads pending either way). The two branch maps are kept SEPARATE, not
    merged: an id can carry a foreign status on one branch and a foreign
    amend on another, and a single merged map would then name the wrong
    branch for whichever envelope block it was not built from (Stage-3 doubt
    review, finding 2 — constructed with real data: a status on branch B and
    an amend on branch A for the same id, a merged map reports B for both,
    which is false for the amend). Empty at no extra cost — not even a
    directory listing — on any tree that is not a main tree, or has no
    siblings.
    """
    foreign = foreign_records_by_branch(project_root)
    if not foreign:
        return set(), set(), {}, {}
    root = Path(project_root)
    tracked = _cached_records(root / _SHIPWRIGHT_DIR / _TRIAGE_FILE)
    outbox = _cached_records(root / _SHIPWRIGHT_DIR / _OUTBOX_FILE)
    cross_status = foreign_undelivered_from_records(
        tracked, outbox, foreign, applied_statuses=applied_statuses)
    cross_amends = foreign_undelivered_amends_from_records(
        tracked, foreign, is_valid_amend=is_valid_amend)
    return set(cross_status), set(cross_amends), dict(cross_status), dict(cross_amends)


def foreign_status_and_amend_records(project_root: Path | str) -> list[dict]:
    """Bare ``status``/``amend`` event dicts from every sibling's tracked log,
    flattened across branches.

    ``foreign_records_by_branch`` already filters to these two kinds before
    caching (never ``append`` — folding a foreign append would seed an item
    this tree never created itself, see the module boundary note); this just
    drops the per-branch grouping that :func:`triage.read_all_items`'s pass 2
    (which discards any event whose id it does not already know) has no use
    for.
    """
    return [
        raw
        for _branch, records in foreign_records_by_branch(project_root)
        for raw in records
    ]
