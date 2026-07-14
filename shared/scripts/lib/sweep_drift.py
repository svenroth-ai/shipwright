"""Adopt undelivered main-tree TRACKED triage drift into the outbox (the real
delivery channel).

iterate-2026-07-14-sweep-drift-dismiss-loss. ``.shipwright/triage.jsonl`` is tracked, so
an append that lands there while still UNCOMMITTED is delivered by nothing: the D2 sweep
folds only the gitignored outbox, and :func:`lib.reconcile_triage.reconcile_main_triage`
is a manual operator CLI no pipeline calls. The append rots in the working tree —
invisible to ``origin`` and to every worktree, which branch off ``origin/<default>``.
Worse, a ``status`` for such an append looked like an ORPHAN to the sweep's validator and
was quarantined away, so the operator's dismiss was silently destroyed on every sweep and
the item resurrected on the board forever (reproduced in shipwright-webui, 2026-07-14).

**Plan, then commit.** :func:`plan_main_tracked_drift` only READS: it decides whether the
drift is adoptable and returns the lines it would move. Nothing is mutated until the
caller — which by then knows whether the resulting log even validates — calls
:func:`commit_main_tracked_drift`. That ordering is load-bearing: mutating first would
move the operator's data out of the git-tracked log into a GITIGNORED buffer and only
then discover the sweep must abort, leaving main's ``git status`` clean while the only
copy of that data sits in a file ``git clean -x`` deletes.

The plan refuses (mutating NOTHING) unless it fully understands main's state:

* **append-only prefix** — the working log's lines must START WITH HEAD's complete line
  sequence, compared VERBATIM. A removed, edited (incl. whitespace-only), reordered,
  emptied or deleted line is not drift we can reason about → ``main_tracked_diverged``.
  A set-difference test would wave all of those through (external review).
* **clean index** — a STAGED triage delta means restoring the working file alone would
  leave the drift in the index, and a later commit on main would reintroduce it →
  ``main_tracked_index_diverged``.
* **well-formed drift** — every adoptable line must be a producer event, so adoption can
  never poison the outbox with corruption whose source it then hides by rewriting the
  tracked file → ``main_tracked_unparseable``.

``unrepairable`` is the third outcome and is NOT a refusal: a state we understand but
cannot repair (no HEAD blob to restore to — e.g. local main is behind origin, or the
blob carries no header). Nothing is mutated, but the caller may PROCEED: stranding every
pending append over a benign repo shape would trade one delivery failure for another.

**Crash-safety.** :func:`commit_main_tracked_drift` writes the outbox durably FIRST and
restores the tracked log second. An interruption between them leaves the drift in both
places — harmless, because the plan dedups candidates against the outbox, so the replay
adds nothing and simply completes the restore. Never the other order (that one loses
data). The restore is ``git checkout -- <log>``, not a hand-written file: the index guard
guarantees index == HEAD, so git reproduces HEAD's bytes honouring ``core.autocrlf`` and
``.gitattributes``. Reconstructing them by hand meant guessing the EOL from the working
file, and one CRLF drift line over an LF checkout rewrote the ENTIRE log as CRLF.

The caller (:mod:`lib.sweep_outbox`) runs both halves INSIDE the canonical triage
``_FileLock``, in the same critical section that reads and folds the outbox, so a
background producer never races the read-plan-commit transaction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lib.atomic_write import durable_atomic_write
from lib.churn_merge import TRIAGE_LOG
from lib.sweep_text import normalize_lines, read_text_verbatim
from lib.worktree_isolation import run_git

#: Producer event kinds a drift line may carry. Anything else is not a line this module
#: is willing to move (and therefore not one it is willing to delete from the log either).
_EVENTS = frozenset({"append", "status"})


@dataclass(frozen=True)
class DriftPlan:
    """What :func:`plan_main_tracked_drift` WOULD do. Nothing has been mutated yet.

    ``status`` ∈ {``adoptable``, ``no_drift``, ``unrepairable``, ``refused``}:

    * ``adoptable``    — ``drift`` can be moved into the outbox; call the commit half.
    * ``no_drift``     — main's tracked log is already delivered; nothing to do.
    * ``unrepairable`` — understood but not repairable (no HEAD blob / headerless blob).
      Mutates nothing; the caller MAY proceed with the rest of the sweep.
    * ``refused``      — main's state is one we do NOT understand. The caller must STOP.

    ``drift`` is every undelivered line (the count the operator is told about); ``fresh``
    is the subset not already buffered in the outbox (a crash replay re-plans the same
    drift and must not double-buffer it). ``known_append_ids`` is the read-only universe
    of append ids in main's tracked log — returned on EVERY outcome, because the sweep
    needs it to tell a legitimate status from a genuine orphan whether or not the repair
    can run.
    """

    status: str
    reason: str = ""
    drift: list[str] = field(default_factory=list)
    fresh: list[str] = field(default_factory=list)
    known_append_ids: frozenset[str] = frozenset()
    _raw: str = ""
    _head_oid: str = ""


@dataclass(frozen=True)
class DriftResult:
    """Outcome of :func:`commit_main_tracked_drift`.

    ``status`` ∈ {``adopted``, ``buffered``, ``error``}. ``buffered`` means the outbox
    write landed but the restore was abandoned because HEAD or the file moved under us —
    no loss (the replay completes it), but the operator is told the truth rather than
    "adopted". ``adopted`` is the count of drift lines moved, reported on every outcome
    including ``buffered``, where it would otherwise read as 0.
    """

    status: str
    reason: str = ""
    adopted: int = 0


def append_ids_of(lines: list[str]) -> frozenset[str]:
    """Ids of every well-formed ``append`` event in ``lines``.

    Only valid, unambiguous appends enter the universe (external review): a line that does
    not parse, is not an object, or carries a non-``str`` id contributes nothing — it must
    never protect a status from the orphan check.
    """
    ids: set[str] = set()
    for line in lines:
        obj = _parsed(line)
        iid = obj.get("id") if obj else None
        if obj and obj.get("event") == "append" and isinstance(iid, str):
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


def _is_producer_event(line: str) -> bool:
    """True iff ``line`` is a well-formed triage producer event (append / status with a
    str id) — the only shape adoption is willing to move."""
    obj = _parsed(line)
    return bool(obj) and obj.get("event") in _EVENTS and isinstance(obj.get("id"), str)


def _is_header(line: str) -> bool:
    obj = _parsed(line)
    return bool(obj) and obj.get("schema") == "triage" and "v" in obj


def _head_lines(main_root: Path) -> list[str] | None:
    """Lines of ``HEAD:<triage>`` in MAIN's tree VERBATIM, or ``None`` when there is no
    such blob. ``cwd=main_root`` is load-bearing: ``HEAD`` must be main's branch tip, NOT
    the iterate worktree's (external review)."""
    proc = run_git(["show", f"HEAD:{TRIAGE_LOG}"], cwd=main_root, check=False)
    if proc.returncode != 0:
        return None
    lines, _ = normalize_lines(proc.stdout)
    return lines


def _head_oid(main_root: Path) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=main_root, check=False).stdout.strip()


def _index_diverged(main_root: Path) -> bool:
    """True when the triage log has a STAGED delta against HEAD."""
    probe = run_git(["diff", "--cached", "--quiet", "--", TRIAGE_LOG], cwd=main_root, check=False)
    return probe.returncode != 0


def _events(lines: list[str]) -> list[str]:
    """Non-blank lines, VERBATIM. Blanks carry no event, so a stray one must not refuse a
    legitimate repair — but everything else is compared exactly as written."""
    return [ln for ln in lines if ln.strip()]


def plan_main_tracked_drift(main_root: Path | str, outbox_path: Path) -> DriftPlan:
    """Decide what (if anything) to adopt from main's TRACKED triage log. READ-ONLY —
    mutates nothing, so the caller can still abort after seeing the resulting log."""
    main_root = Path(main_root)
    triage_path = main_root / TRIAGE_LOG

    raw = read_text_verbatim(triage_path)
    lines, _eol = normalize_lines(raw)
    known = append_ids_of(lines)

    # HEAD is read BEFORE the empty-file shortcut: a MISSING or EMPTIED working log whose
    # HEAD blob has content is not "no drift", it is the severest divergence there is —
    # every HEAD line is gone. Shortcutting would let the sweep proceed over a state it
    # never compared (external review).
    head = _head_lines(main_root)
    if head is None:
        if not raw:
            return DriftPlan("no_drift", known_append_ids=known)
        return DriftPlan("unrepairable", reason="main_tracked_no_head_blob", known_append_ids=known)

    head_events, work_events = _events(head), _events(lines)
    if work_events[: len(head_events)] != head_events:
        return DriftPlan(
            "refused",
            reason=f"main_tracked_diverged: the working log is not an append-only extension of "
                   f"HEAD ({len(head_events)} HEAD line(s), {len(work_events)} in the working tree)",
            known_append_ids=known,
        )

    drift = work_events[len(head_events):]
    if not drift:
        return DriftPlan("no_drift", known_append_ids=known)
    if any(_is_header(ln) for ln in drift):
        # The schema header fell inside the drift window (HEAD's blob is empty or
        # headerless). The outbox is headerless BY DESIGN, so the header is not ours to
        # move — but this is a benign log shape, not corruption, and must not be reported
        # as such nor block delivery forever.
        return DriftPlan("unrepairable", reason="main_tracked_headerless_head_blob", known_append_ids=known)
    if _index_diverged(main_root):
        return DriftPlan(
            "refused",
            reason="main_tracked_index_diverged: the triage log has a staged delta — restoring "
                   "the working file alone would leave the drift in the index",
            known_append_ids=known,
        )
    bad = next((n for n, ln in enumerate(drift, start=1) if not _is_producer_event(ln)), None)
    if bad is not None:
        return DriftPlan(
            "refused",
            reason=f"main_tracked_unparseable: drift line {bad} is not a triage producer event",
            known_append_ids=known,
        )

    buffered, _ = normalize_lines(read_text_verbatim(outbox_path))
    already = {ln.strip() for ln in buffered if ln.strip()}
    return DriftPlan(
        "adoptable",
        drift=drift,
        fresh=[ln for ln in drift if ln.strip() not in already],
        known_append_ids=known,
        _raw=raw,
        _head_oid=_head_oid(main_root),
    )


def commit_main_tracked_drift(
    plan: DriftPlan, main_root: Path | str, outbox_path: Path
) -> DriftResult:
    """Execute an ``adoptable`` plan: buffer the drift into the outbox (durably, FIRST),
    then restore main's tracked log to HEAD via git. Call ONLY under the caller's lock,
    and only once the resulting log is known to validate."""
    main_root = Path(main_root)
    triage_path = main_root / TRIAGE_LOG

    # 1. Outbox first, durably. An interruption after this is harmless: the replay re-plans
    #    the same drift, finds it buffered (``fresh`` is empty), and completes the restore.
    if plan.fresh:
        buffered, outbox_eol = normalize_lines(read_text_verbatim(outbox_path))
        keep = [ln for ln in buffered if ln.strip()]
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        durable_atomic_write(outbox_path, outbox_eol.join(keep + plan.fresh) + outbox_eol)

    # 2. Restore — but only if nothing moved under us. A process lock cannot stop an
    #    external `git commit` or an editor, so re-read both anchors first.
    if _head_oid(main_root) != plan._head_oid or read_text_verbatim(triage_path) != plan._raw:
        return DriftResult(
            "buffered",
            reason="main_tracked_changed_during_adopt: HEAD or the tracked log moved mid-repair "
                   "— the drift is buffered in the outbox; the next sweep completes the restore",
            adopted=len(plan.drift),
        )
    # git, not a hand-written file: the index guard proved index == HEAD, so `checkout --`
    # reproduces HEAD's exact bytes under core.autocrlf / .gitattributes. Guessing the EOL
    # from the working file rewrote the whole log as CRLF the moment one drift line was.
    restore = run_git(["checkout", "--", TRIAGE_LOG], cwd=main_root, check=False)
    if restore.returncode != 0:
        return DriftResult(
            "buffered",
            reason=f"main_tracked_restore_failed: {restore.stderr.strip()[:200]} — the drift is "
                   f"buffered in the outbox; the next sweep completes the restore",
            adopted=len(plan.drift),
        )
    return DriftResult("adopted", adopted=len(plan.drift))
