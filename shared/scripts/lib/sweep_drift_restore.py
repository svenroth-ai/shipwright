"""Restore main's tracked triage log to HEAD **without overwriting a late append**.

Extracted from :mod:`lib.sweep_drift` (audit 2026-07-28, finding 23).

**The window.** ``commit_main_tracked_drift`` buffers the drift into the outbox,
re-reads HEAD and the tracked file to confirm nothing moved, and then runs
``git checkout -- <log>``. Between that last read and git's write there is a
subprocess spawn — tens to hundreds of milliseconds on Windows. A writer that does
not take the canonical triage lock (the WebUI uses ``proper-lockfile``, which does
not compose with the Python byte lock — ``triage_repair.py:30-36``) can append in
it, and ``git checkout`` then overwrites the file. The append is gone, nothing
observed it, and the sweep reports success. The re-verification narrows that window
and cannot close it, which the old code described as unavoidable.

**It is not unavoidable — it is a data-loss window, and this module closes the
dominant part of it.** Instead of letting git overwrite the live file, we
``os.replace`` the file aside first. That rename is atomic, so whatever the log
held at that instant is preserved in the salvage file rather than clobbered; git
then recreates the path from HEAD with nothing of ours underneath it. Afterwards
the salvage is compared to what the plan read: identical means nothing was lost,
and a well-formed appended suffix is adopted into the outbox — recovered rather
than destroyed.

**What genuinely remains**, stated plainly rather than hidden: a writer that opens
the path *by name* between the rename and git's write creates a new file that
``checkout`` then overwrites. That window is a fraction of the original (no
subprocess inside it) but it is not zero, and it is real data loss when it happens.

The salvage lives beside the log in ``.shipwright/``, which ``/.shipwright/*``
already gitignores, so it never becomes tracked drift of its own. It is removed only
once the restore AND any adoption have both succeeded; on every ambiguous failure it
is left on disk and named in the reason.

**The gitignoring cuts both ways, and the retained case is the sharp edge.** On the
``unadopted`` / ``needs_review`` / ``not_an_extension`` paths the salvage is the ONLY
copy of that content — and it sits in a file ``git clean -xfd`` deletes. That is the
same hazard :mod:`lib.sweep_drift` refuses for the outbox ("the only copy of that data
sits in a file ``git clean -x`` deletes"), accepted here for a narrower case: the
alternative is overwriting the content outright, which is what this module exists to
stop. The reasons therefore say "do not delete it" and name the file, and
:func:`lib.sweep_result.sweep_warnings` prints them on an otherwise-successful sweep.
An operator who runs ``git clean -xfd`` on an unread warning still loses it.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from lib.atomic_write import durable_atomic_write, replace_retrying
from lib.churn_merge import TRIAGE_LOG
from lib.git_base import TIMEOUT_RETURNCODE, run_git_soft
from lib.sweep_drift_events import _is_glued_producer_line, _is_producer_event, _REPAIR_HINT
from lib.sweep_text import normalize_lines, read_text_verbatim

#: Cap on the per-pid salvage-name search. A three-digit collision run means
#: something is very wrong; failing loudly beats spinning.
_SALVAGE_ATTEMPTS = 100


def _claim_salvage_path(triage_path: Path) -> Path:
    """Reserve an unused sibling path with ``O_EXCL`` so two processes cannot pick
    the same one and one silently clobber the other's preserved bytes."""
    for n in range(_SALVAGE_ATTEMPTS):
        candidate = triage_path.with_name(f"{triage_path.name}.salvage-{os.getpid()}-{n}")
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise RuntimeError(f"sweep_drift_restore: no free salvage name beside {triage_path}")


def _drop_salvage(path: Path) -> None:
    """Remove a salvage file we no longer need. Best-effort: failing to clean up a
    gitignored scratch file must never fail a sweep that otherwise succeeded."""
    with contextlib.suppress(OSError):
        path.unlink()


def _adopt_late_lines(late: list[str], outbox_path: Path) -> int:
    """Append genuinely-new late lines to the outbox durably. Idempotent: a replay
    dedups against what is already buffered, exactly as ``plan.fresh`` does."""
    buffered, eol = normalize_lines(read_text_verbatim(outbox_path))
    keep = [ln for ln in buffered if ln.strip()]
    already = {ln.strip() for ln in keep}
    fresh = [ln for ln in late if ln.strip() not in already]
    if not fresh:
        return 0
    outbox_path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(
        outbox_path, (eol.join(keep + fresh) + eol).encode("utf-8", errors="surrogateescape"))
    return len(fresh)


def _classify_salvage(salvage: Path, planned_raw: str) -> tuple[str, list[str]]:
    """``("identical" | "late_append" | "unparseable" | "not_an_extension", lines)``.

    Only a well-formed producer-event suffix of exactly what the plan read may be
    adopted. Everything else — a truncation, a wholesale rewrite, a half-written
    line — is preserved for a human instead, because treating any difference as a
    late append would convert corruption into apparently valid delivery input.
    """
    text = read_text_verbatim(salvage)
    if text == planned_raw:
        return "identical", []
    if not text.startswith(planned_raw):
        return "not_an_extension", []
    suffix, _eol = normalize_lines(text[len(planned_raw):])
    late = [ln for ln in suffix if ln.strip()]
    if not late or not all(_is_producer_event(ln) for ln in late):
        # ``late`` (not ``[]``) even here: the caller inspects it to tell a glued-but-
        # recoverable line apart from genuine corruption in the reason it composes
        # (doubt review, medium) — nothing here is adopted differently either way.
        return "unparseable", late
    return "late_append", late


def restore_tracked_log(
    main_root: Path, triage_path: Path, outbox_path: Path, planned_raw: str
) -> tuple[str, str, int]:
    """Replace the tracked log with HEAD's content, preserving anything that landed
    late. Returns ``(status, reason, late_adopted)`` with ``status`` ∈
    {``adopted``, ``buffered``, ``error``}; the caller maps it onto its own result
    type. ``error`` is reserved for the one outcome that is not recoverable by a
    replay: the tracked log is MISSING because git failed to recreate it and our
    put-back failed too. A soft ``buffered`` there would be read as "the next sweep
    completes the restore", which is false.

    Never raises for an expected condition — the sweep runs during worktree setup
    and an exception here strands a half-created worktree.
    """
    try:
        salvage = _claim_salvage_path(triage_path)
    except (OSError, RuntimeError) as exc:
        return "buffered", f"main_tracked_salvage_unavailable: {exc} — the drift is buffered " \
                           "in the outbox; the next sweep completes the restore", 0
    try:
        replace_retrying(triage_path, salvage)
    except OSError as exc:
        # Do NOT fall back to a bare `checkout`: that is precisely the overwrite this
        # module exists to prevent. Abort the restore instead — the drift is safe in
        # the outbox and the next sweep re-plans it (the documented replay path).
        _drop_salvage(salvage)
        return "buffered", (f"main_tracked_salvage_rename_failed: {exc} — nothing was "
                            "overwritten; the drift is buffered in the outbox and the next "
                            "sweep completes the restore"), 0

    restore = run_git_soft(["checkout", "--", TRIAGE_LOG], cwd=main_root)
    if restore.returncode != 0:
        detail = ("`git checkout` was killed mid-restore" if restore.returncode == TIMEOUT_RETURNCODE
                  else f"`git checkout` failed: {restore.stderr.strip()[:200]}")
        if not triage_path.exists():
            # Nothing is at the path, so putting our bytes back cannot clobber anyone —
            # but only at the instant of that check. A BARE replace here, deliberately,
            # unlike the rename-aside above: the retry's ONLY trigger on Windows is a
            # sharing violation, whose canonical cause on a rename is a destination that
            # exists and is held open. That is precisely the state `exists()` just ruled
            # out, so retrying would mean waiting for the WebUI writer to release a file
            # it recreated after our check, and then destroying it. Failing immediately
            # drops into the keep-both arm below instead (doubt review).
            try:
                os.replace(salvage, triage_path)
            except OSError as exc:
                # NOT ``buffered``: that word promises the next sweep completes the
                # restore, and nothing can complete a restore of a file that is gone.
                return "error", (f"main_tracked_restore_failed: {detail}, AND the log could "
                                 f"not be put back ({exc}). The tracked log is MISSING; its "
                                 f"content is at {salvage.name}. Restore it by hand."), 0
            return "buffered", (f"main_tracked_restore_failed: {detail} — the log was put back "
                                "unchanged and the drift is buffered in the outbox"), 0
        # Something IS at the path — a partial checkout artifact, or a writer that
        # opened it after our rename. Overwriting it with the salvage would recreate
        # the loss mode. Keep both and hand it to a human.
        return "buffered", (f"main_tracked_restore_ambiguous: {detail}, and a file reappeared at "
                            f"{TRIAGE_LOG} afterwards. BOTH were kept — the pre-restore content "
                            f"is at {salvage.name}; compare them before deleting either"), 0

    try:
        verdict, late = _classify_salvage(salvage, planned_raw)
    except OSError as exc:
        # The ONE unguarded read in a function contracted never to raise (an exception
        # here strands a half-created worktree, AFTER the log has been renamed aside —
        # so the salvage would be orphaned with nothing naming it). Code review, HIGH.
        return "adopted", (f"main_tracked_salvage_unclassified: {exc} — the pre-restore "
                           f"content is preserved at {salvage.name}; review before deleting"), 0
    if verdict == "identical":
        _drop_salvage(salvage)
        return "adopted", "", 0
    if verdict == "late_append":
        try:
            adopted = _adopt_late_lines(late, outbox_path)
        except OSError as exc:
            return "adopted", (f"main_tracked_salvage_unadopted: {len(late)} line(s) landed during "
                               f"the restore and could not be buffered ({exc}); they are preserved "
                               f"at {salvage.name} — do not delete it"), 0
        _drop_salvage(salvage)  # only now: the bytes are durably elsewhere
        # BOTH counts: on an idempotent replay `adopted` is 0 because the lines were
        # already buffered, and "0 append(s) recovered" reads as nothing happened.
        note = (f"main_tracked_late_append_salvaged: {len(late)} append(s) landed during the "
                f"restore and were preserved rather than overwritten ({adopted} newly buffered; "
                f"any remainder was already in the outbox)")
        return "adopted", note, adopted
    if verdict == "unparseable" and any(_is_glued_producer_line(ln) for ln in late):
        # Same glued shape :func:`lib.sweep_drift_events._bad_drift_reason` names for the
        # plan path — surfaced here too (doubt review, medium): this branch already
        # reports the sweep as ``adopted`` (success), so an unnamed remedy would be
        # easier to miss than an outright refusal.
        reason = ("main_tracked_salvage_glued_line: the log gained a line during the restore "
                  f"that holds a recognisable triage producer event glued to other content; "
                  f"{_REPAIR_HINT}")
    elif verdict == "unparseable":
        reason = ("main_tracked_salvage_needs_review: the log gained content during the restore "
                  "that is not a well-formed producer append")
    else:
        reason = ("main_tracked_salvage_not_an_extension: the log was rewritten (not appended to) "
                  "during the restore")
    return "adopted", f"{reason}; it is preserved at {salvage.name} — review before deleting", 0
