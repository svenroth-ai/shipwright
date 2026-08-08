"""F11 pointer retirement (trg-276994a4).

Split into its own module rather than added to ``worktree_isolation.py`` or
``deliver_pr.py`` — both are already at their ``shipwright_bloat_baseline.json``
ceiling (zero headroom; any growth ratchets and blocks the commit), and this
is genuinely new behavior, not a natural extension of either file's existing
job. ``worktree_isolation.py`` owns the pointer's read/write shape;
``deliver_pr.py`` owns the delivery ladder. Retirement is neither — it is the
seam between "the run is DELIVERED (or CLOSED unmerged)" (deliver_pr's fact)
and "the pointer should stop resolving" (worktree_isolation's data) — so it
gets its own file.

**Keyed on ``run_id``, not ``session_id``.** An earlier version located the
pointer file by ``session_id`` (mirroring ``read_run_pointer``), but the only
``run_id``-bearing caller (``deliver_pr.py``'s CLI) sources ``session_id`` from
``$SHIPWRIGHT_SESSION_ID``, which is not guaranteed to reach the delivery
subprocess's environment — a silent no-op would leave the original defect
unfixed with every gate still green. ``run_id`` is a required CLI argument
with no such dependency, and it is already the field ``retire_run_pointer``
must match before unlinking anything, so scanning every pointer file's own
recorded ``run_id`` is both more robust and the actual ownership check (a
pointer's filename is not proof of what it names — see ``pointer_run_id``'s
own ``payload_session`` comment in ``lib/phase_quality/_run_id.py``). It
unlinks EVERY pointer naming ``run_id``, not just the first match found: two
pointer files can legitimately name the same run (a resumed iterate driven
from a second session writes a second, differently-keyed pointer for the
same ``run_id`` — ``setup_iterate_worktree.setup()``'s in-worktree branch),
and leaving a second one behind would report success while the original
defect stayed live for whichever session owns the surviving file.

**Other readers of this same pointer.** Retiring it changes what THREE other
consumers see on the next Stop event in the same session, once F11 has run
(none of them read it during the live run, since none of the corresponding
Stops fire before DELIVERED/CLOSED — F12 is the last step, after F11, per
the iterate SKILL): ``iterate_stop_finalize._active_worktree_root`` (falls
back to no worktree, so its repair-finalize pass is gated off — desired,
since a merged/closed run has nothing left to finalize); and
``context_cost_session.resolve_active_project_root``, read by both
``track_context_cost.py`` and ``context_cost_statusline.py`` (both fall back
to the MAIN root for any further cost samples in the session — desired, the
same tree the operator's own cwd is in once the worktree's purpose is done).
None of the three needs the pointer to keep resolving a run that is over.

**Deliberately does NOT trigger on ``EXIT_NO_MERGER`` (doubt-review D2).**
``deliver_pr.py``'s exit 6 means "NOT DELIVERED — merge it by hand, or
re-run with self-merge enabled" (see F11.md's own delivery-outcome table) —
the run is NOT over, it is blocked pending a human. Retiring the pointer on
that exit would be premature: an operator who re-runs ``deliver_pr.py``
after fixing the blocker (the documented remedy) needs the SAME pointer
still resolvable for THIS SAME run, or the redirect this iterate's other
fix relies on (trg-b36fd844) goes dark mid-run. The one path this leaves
genuinely open is a same-session hand-merge followed by continued work in
that session without running the pre-existing worktree cleanup step
(``git worktree remove`` — already documented in the iterate SKILL's B1a).
That window is bounded by ``pointer_worktree_root``'s own ``worktree.is_dir()``
check, not by retirement: once the worktree is removed, the stale pointer
stops redirecting regardless. Closing it fully needs a mechanism that
observes the PR's merged state independently of this repo's own delivery
path (e.g. polling the host after telling the operator to merge by hand) —
a new capability, out of scope for this fix.

**Unlink, not a ``retired`` flag (doubt-review delta pass, D7).** The spec's
required shape offered either. A flag the resolver checks would be equally
correct and idempotent, but ``unlink`` was kept: retirement already scans
every pointer file each call (no per-file state to reconcile), a flag adds a
write-then-read contract two consumers would each need to honor rather than
one boolean "does the file still exist", and this directory already holds
nothing but live-or-stale pointers with no other archival purpose — turning
a defunct pointer into an inert file with no reader left to prune it just
relocates the original problem (a directory that answers queries for runs
that are over) one field deeper instead of closing it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lib.repo_root import resolve_main_repo_root
from lib.worktree_isolation import ACTIVE_POINTER_DIRNAME


def retire_run_pointer(main_root: Path, run_id: str) -> bool:
    """Unlink every run pointer naming ``run_id`` once it is DELIVERED/CLOSED.

    ``prune_stale_run_pointers`` (``worktree_isolation.py``) only reaps a
    pointer whose *worktree* is gone — but a worktree is routinely RETAINED
    after its PR merges (this repo does not auto-remove it), so
    ``pointer_run_id``'s liveness check keeps resolving a run that has
    actually finished for the rest of the session, misattributing later
    Stop-hook audits to it. F11 calls this the moment ``deliver_pr.py``
    reaches a terminal delivery outcome for the run — the run's own
    definition of "finished" — giving the pointer an explicit end-of-run
    signal that does not depend on the worktree directory ever being
    deleted.

    Scans every pointer file rather than a single computed path: a session
    that has since started a NEW iterate overwrites its own session-keyed
    pointer, so a late-finishing delivery call for the OLD run must match on
    the OLD run's own recorded ``run_id`` — never on filename alone — or it
    would retire the new run's live pointer instead. Returns True iff at
    least one pointer was unlinked; a per-file unlink failure (external
    review, e.g. a permission error on one of several matches) is printed to
    stderr rather than silently dropped, so a PARTIAL retirement — some
    matches removed, one still live — is never indistinguishable from a
    clean success.

    Requires ``worktree_path`` in the parsed payload before treating a file
    as a real pointer (external review): a stray non-pointer JSON dropped
    into this directory that happens to carry a matching ``run_id`` field
    must not be deleted just because the key it was matched on collides.
    """
    run_id = (run_id or "").strip()
    if not run_id:
        return False
    pointer_dir = main_root / ".shipwright" / ACTIVE_POINTER_DIRNAME
    unlinked = 0
    for path in sorted(pointer_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or "worktree_path" not in data:
            continue
        if str(data.get("run_id") or "").strip() != run_id:
            continue
        # Re-check immediately before unlinking (doubt-review D3): the pointer
        # is session_id-keyed and `write_run_pointer` uses an atomic replace
        # (new inode, same path), so a same-session write between the read
        # above and this unlink — e.g. a campaign's next sub-iterate reusing
        # the same session id — could otherwise delete a brand-new pointer
        # for a DIFFERENT run under the OLD one's name. This narrows, not
        # eliminates, the window: still not a single atomic check-and-delete,
        # but shrinks it from "the whole glob loop" to "one extra stat+read".
        try:
            recheck = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(recheck, dict) or str(recheck.get("run_id") or "").strip() != run_id:
            continue
        try:
            path.unlink()
        except OSError as exc:
            print(
                f"[run_pointer_retirement] could not unlink {path} "
                f"(run_id={run_id!r}): {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            continue
        unlinked += 1
    return unlinked > 0


def retire_run_pointer_best_effort(project_root: Path, run_id: str) -> bool:
    """CLI-facing wrapper for a caller (``deliver_pr.py``) that resolves
    ``project_root`` from a worktree and must never let pointer housekeeping
    affect its own exit code.

    Prints one diagnostic line to stderr on any non-retirement outcome — a
    silent no-op here is exactly the failure class the ``session_id`` ->
    ``run_id`` redesign exists to eliminate; swallowing the result without a
    trace would reintroduce it as an unobservable one instead.
    """
    try:
        main_root = resolve_main_repo_root(project_root) or project_root
        retired = retire_run_pointer(main_root, run_id)
    except Exception as exc:  # noqa: BLE001 — housekeeping must never break delivery
        print(
            f"[run_pointer_retirement] pointer retirement failed for "
            f"run_id={run_id!r}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False
    if not retired:
        # Deliberately does NOT assert "no pointer matched" — a matching
        # pointer whose unlink failed already printed its own specific
        # diagnostic above (code-review: the two messages must not
        # contradict each other when a match existed but couldn't unlink).
        print(
            f"[run_pointer_retirement] pointer retirement did not complete for "
            f"run_id={run_id!r} under "
            f"{main_root / '.shipwright' / ACTIVE_POINTER_DIRNAME} "
            "(no match, or see the per-file error above)",
            file=sys.stderr,
        )
    return retired


__all__ = ["retire_run_pointer", "retire_run_pointer_best_effort"]
