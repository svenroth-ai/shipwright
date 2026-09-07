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
* **Ordinary file reads, no git subprocess.** ``main``-vs-``worktree`` and a
  worktree's checked-out branch are both derived from ``.git`` file contents
  (a linked worktree's ``.git`` is a FILE naming its admin dir, whose
  ``HEAD`` names the branch), never a ``git`` call — a subprocess per
  ``read_all_items`` call would be the wrong trade for a fact that never
  changes mid-process. A non-absolute ``gitdir:`` target (relative worktree
  paths, git >= 2.48) is resolved against the worktree's own directory, not
  the process CWD, so that config can't silently disable every sibling at once.
* **Cache the PARSE, not the discovery walk** (``_CACHE``, keyed on
  ``(path, mtime)``). An earlier version also cached
  :func:`sibling_worktree_logs`'s directory walk on ``.worktrees``' own mtime,
  which missed a sibling gaining a `triage.jsonl` after the first scan, or
  switching its checked-out branch — neither changes `.worktrees`' own mtime
  or listing (PR #684 review). The walk is now unconditional on every call;
  it stays cheap (an ``iterdir`` plus a few small reads per sibling) precisely
  because the one genuinely expensive part — parsing a sibling's full log,
  some exceeding a thousand records with multi-kilobyte fields — is what
  ``_CACHE`` amortizes across the several ``read_all_items`` calls one CLI
  invocation makes. Process-lifetime only, by design — a fresh process per
  invocation means it never amortizes ACROSS invocations (a WebUI poll pays
  the full parse cost every time); fixing that would need a persistent cache,
  out of scope here.
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
_WORKTREES_DIRNAME = ".worktrees"

#: (path, mtime) -> parsed records. Process-lifetime only, by design (see module
#: docstring) — not a correctness risk: a stale hit only ever costs a re-read on
#: the NEXT process, since nothing here is ever the writer.
_CACHE: dict[Path, tuple[float, list[dict]]] = {}


def _is_main_tree(root: Path) -> bool:
    """True iff ``root`` is a main working tree, not a linked git worktree.

    A linked worktree's ``.git`` is a FILE (``gitdir: <path>``); the main
    tree's is a directory. Pure filesystem check — see module docstring.
    """
    return (root / ".git").is_dir()


def _branch_name(worktree_dir: Path) -> str | None:
    """Branch checked out in ``worktree_dir``, or ``None`` if it cannot be named
    (not a linked worktree, unreadable admin dir, or a detached ``HEAD``).

    Both reads are plain files: the worktree's own ``.git`` names its admin
    directory (``.git/worktrees/<name>``), whose ``HEAD`` holds either
    ``ref: refs/heads/<branch>`` or a raw commit SHA (detached).
    """
    git_marker = worktree_dir / ".git"
    try:
        text = git_marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    prefix = "gitdir:"
    line = next(
        (ln for ln in text.splitlines() if ln.strip().startswith(prefix)), None,
    )
    if line is None:
        return None
    admin_dir = Path(line.split(":", 1)[1].strip())
    if not admin_dir.is_absolute():
        # git >= 2.48 / worktree.useRelativePaths can write a relative
        # target; resolve it against the worktree's own directory, never the
        # process CWD, or every sibling silently loses this feature at once
        # (Stage-3 doubt review, finding 7).
        admin_dir = (worktree_dir / admin_dir).resolve()
    try:
        head = (admin_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return None  # detached HEAD — no branch to name
    return head[len("ref:") :].strip().removeprefix("refs/heads/")


def sibling_worktree_logs(project_root: Path | str) -> list[tuple[str, Path]]:
    """``(branch, path)`` for every sibling worktree's TRACKED triage log.

    Empty unless ``project_root`` is the MAIN tree. A sibling directory with
    no tracked log, or whose branch cannot be named, is skipped rather than
    guessed at — reporting nothing beats reporting something unattributed.

    **Not cached — walked fresh on every call, deliberately** (PR #684
    review round). An earlier version memoized this walk on
    ``(.worktrees path, its mtime)``, but a sibling *already* in `.worktrees`
    gaining a `triage.jsonl` after the first scan, or switching its checked-out
    branch (`.git`/`HEAD` rewritten), changes neither `.worktrees`' own mtime
    nor its listing — so that cache could report a sibling as absent, or under
    its old branch, for the rest of the process. The walk itself is cheap
    (one ``iterdir`` plus, per sibling, an ``is_file`` check and up to two
    small text reads for branch identity) — nothing here is the "84 sibling
    worktrees, thousand-record logs" cost :func:`_cached_records` exists to
    amortize; that per-file PARSE is still cached below.
    """
    root = Path(project_root)
    if not _is_main_tree(root):
        return []
    base = root / _WORKTREES_DIRNAME
    if not base.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for wt_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        log_path = wt_dir / _SHIPWRIGHT_DIR / _TRIAGE_FILE
        if not log_path.is_file():
            continue
        branch = _branch_name(wt_dir)
        if branch is None:
            continue
        out.append((branch, log_path))
    return out


def _cached_records(path: Path, *, keep=None) -> list[dict]:
    """Tolerant read of ``path``, memoized on ``(path, mtime)``.

    Mirrors ``triage._iter_raw_lines_at`` (same predicate, same corruption side
    channel) — reimplemented rather than called back into, so this module
    never needs to import :mod:`triage` (that direction is the exact cycle
    ``lib/jsonl_records.py`` documents as this repo's CodeQL cycle origin, per
    :mod:`lib.triage_integrity`'s own docstring).

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
        mtime = path.stat().st_mtime
    except OSError:
        return []
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    result = read_jsonl_records(path, is_record=is_triage_record)
    report_corruption(result.corrupt)
    records = result.records if keep is None else [r for r in result.records if keep(r)]
    _CACHE[path] = (mtime, records)
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
