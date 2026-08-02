"""Capture the tree's dirtiness BEFORE a producer starts writing (``trg-f5ae5371``).

``source_state_git.resolve_git_state`` answers *is the tree dirty right now*. That
is the wrong question for any artifact a producer stamps, because by the time the
producer can ask, it has written its own output into the tree:

* ``finalize_iterate`` appends ``work_completed`` to the TRACKED
  ``shipwright_events.jsonl``, then regenerates compliance;
* ``update_compliance`` rewrites six tracked documents, then emits the
  ``grade_snapshot`` that wants the answer.

So the measurement reads ``dirty=true`` on a pristine tree — evidenced on four
producers, reproduced end-to-end with **zero uncommitted source**. A dirty flag
built that way was withdrawn before commit after two review rounds; an exclusion
list hung off ``DERIVED_SNAPSHOTS`` was rejected in the same review, because that
register deliberately keeps the event log and ``triage.jsonl`` out and the two
answer different questions.

**The distinction that fixes it.** A producer's own writes are the *output* of the
measurement, not its *input*. What a consumer wants to know is whether the tree the
grade was computed FROM held uncommitted work — which is settled before the
producer runs. So the answer is captured at the producer's entry and passed on,
never re-derived later and then corrected by subtraction.

**Transport: the environment.** ``capture_dirty`` records its answer in
``os.environ``, and ``subprocess.run`` inherits the parent environment by default —
so a producer's whole obligation is one call at its entry, with no ``env=``
plumbing at any spawn site. A run-scoped JSON store was planned and dropped after
external review: its only capability the environment lacks is reaching a process
that is not a descendant of the capturer, and that consumer was measured not to
exist (``emit_grade_snapshot`` has exactly one caller; no hook or shell script
invokes ``update_compliance``). See
``.shipwright/planning/iterate/iterate-2026-08-01-grade-snapshot-dirty-capture/external-plan-review.md``.

**Bound to a run AND a tree.** A hashed environment slot preserves each
``(run id, root)`` answer independently; the readable :data:`ENV_DIRTY_RUN` and
:data:`ENV_DIRTY_ROOT` variables mirror the most recent capture and remain the
operator assertion seam. The run id is the same run-id-primary identity
``source_state`` uses, for the same reason (a producer writes before its commit
exists, so a SHA cannot name what it describes); the root is what stops one
process that carries a single run id across two roots from answering for a tree
nobody measured.

**What it counts.** Any *tracked* modification, which is not the same as "source":
a derived artifact written by a **sibling** process earlier in the run counts too
(`trg-709828ad`). The bias is deliberate — ``True`` is the conservative answer, and
a consumer that excludes dirty points loses a point rather than trusting a false
one.

**Three-valued, like the stamp it feeds.** ``True`` / ``False`` / ``None`` =
"git could not answer". Every failure of the measurement *or its environment
transport* degrades to ``None``, the field is then omitted, and the producer is
never taken down by its own metadata. A partial environment write is cleared
best-effort before returning unknown.
"""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from typing import MutableMapping

from source_state import safe_run_id
from source_state_git import resolve_git_root, resolve_git_state

#: ``"1"`` dirty · ``"0"`` clean · absent = the capture ran and git could not
#: answer. Any other value is malformed and reads as unknown — a lenient parse
#: (``bool(value)``, or truthy ``"false"``) would silently assert "clean" about a
#: tree nobody measured, which is the one thing this module exists to prevent.
ENV_DIRTY = "SHIPWRIGHT_SOURCE_DIRTY"

#: The run the capture belongs to. Presence means "this run has been captured",
#: which is what distinguishes a recorded *unknown* from never having asked — the
#: difference between leaving the answer honest and re-measuring a by-then-dirty
#: tree.
ENV_DIRTY_RUN = "SHIPWRIGHT_SOURCE_DIRTY_RUN"

#: The tree the capture was taken in. A run id alone is NOT enough to make an
#: inherited value safe: a process can legitimately carry one run id while acting on
#: more than one root, and honouring the value there would answer for a tree nobody
#: measured. Observed in this repo's own suite, where several tests reuse one run id
#: across per-test fixture repos in a single process (Stage-3 doubt D1). A mismatch
#: re-measures, which is the conservative direction — the worst case is a missed
#: inheritance, never a false assurance.
ENV_DIRTY_ROOT = "SHIPWRIGHT_SOURCE_DIRTY_ROOT"

#: Prefix for the durable-in-the-process-tree slot keyed by ``(run id, root)``.
#: The three readable variables above remain the current-capture mirror (and the
#: operator assertion seam); these hashed slots stop capturing tree B from erasing
#: tree A when one long-lived process serves both. Only the digest enters the
#: environment variable name, so Windows path punctuation and length are harmless.
ENV_DIRTY_SLOT_PREFIX = "SHIPWRIGHT_SOURCE_DIRTY_SLOT_"

_DIRTY_TRUE = "1"
_DIRTY_FALSE = "0"
_DIRTY_UNKNOWN = "?"
_MISSING = object()

Env = MutableMapping[str, str]


def _env(env: Env | None) -> Env:
    return os.environ if env is None else env


def _measure(project_root) -> bool | None:
    """``resolve_git_state``'s dirty bit, degrading to ``None`` on anything odd.

    ``resolve_git_state`` already swallows every git failure, but it calls
    ``Path(project_root)`` unguarded, so a caller passing a non-path type would
    raise straight through the "nothing here raises" contract.
    """
    try:
        return resolve_git_state(project_root).dirty
    except Exception:  # noqa: BLE001 - metadata must never break the producer
        return None


def _root_key(project_root) -> str | None:
    """Stable identity for the tree a capture was taken in, or ``None``.

    Reuse ``source_state_git``'s canonical worktree top-level so a repo root and a
    subdirectory are not mistaken for different trees. If git cannot identify a
    worktree, the resolved caller path is the safe fallback: it can miss inheritance
    and return unknown, but cannot lend another tree a false clean answer.
    """
    try:
        root = Path(project_root).resolve()
        return str(resolve_git_root(root) or root)
    except (TypeError, ValueError, OSError):
        return None


def _slot_name(run: str, root: str) -> str:
    """ASCII-only environment key for one run/tree capture."""
    identity = f"{run}\0{root}".encode("utf-8", errors="surrogatepass")
    return f"{ENV_DIRTY_SLOT_PREFIX}{sha256(identity).hexdigest()}"


def _decode(value) -> bool | None:
    if value == _DIRTY_TRUE:
        return True
    if value == _DIRTY_FALSE:
        return False
    return None


def captured_dirty(
    run_id: str | None, project_root=None, *, env: Env | None = None,
) -> bool | None:
    """The answer already captured for ``run_id`` in ``project_root``, else ``None``.

    ``None`` deliberately conflates "never captured" with "captured, but git could
    not answer": both mean *this artifact cannot say*, which is what a consumer
    needs, and neither may be rendered as a plausible-looking ``False``. The two ARE
    distinguished internally, by :data:`ENV_DIRTY_RUN`, because :func:`capture_dirty`
    must not re-measure in the second case.

    ``project_root`` is checked against :data:`ENV_DIRTY_ROOT` when both are known;
    passing ``None`` skips that check and asks only "what was recorded for this run",
    which is what a caller wants when it has no tree in hand.
    """
    try:
        environ = _env(env)
        run = safe_run_id(run_id)
        if not run:
            return None
        if project_root is not None:
            requested_root = _root_key(project_root)
            if not requested_root:
                return None
            slot_value = environ.get(_slot_name(run, requested_root), _MISSING)
            if slot_value is not _MISSING:
                return _decode(slot_value)
            recorded_root = environ.get(ENV_DIRTY_ROOT)
            # Missing is not a wildcard. Without both identities there is no proof
            # that the inherited answer describes the requested tree.
            if (environ.get(ENV_DIRTY_RUN) != run or not recorded_root
                    or recorded_root != requested_root):
                return None
        elif environ.get(ENV_DIRTY_RUN) != run:
            return None
        return _decode(environ.get(ENV_DIRTY))
    except Exception:  # noqa: BLE001 - metadata transport must never break a producer
        return None


def capture_dirty(
    project_root, run_id: str | None = None, *, env: Env | None = None
) -> bool | None:
    """Return this run's dirtiness, measuring it at most once **per process tree**.
    **First call wins.**

    "Per process tree" is the honest bound, not "per run": the answer travels by
    environment inheritance, so a *sibling* process in the same run — one spawned by
    a common ancestor rather than by the capturer — measures independently. That
    residual is `trg-709828ad`.

    Call this at a producer's entry, BEFORE it writes anything. A later call in the
    same run — including from a subprocess, which inherits the environment — returns
    what the first call saw, not the tree the producer has since dirtied.

    Without a usable ``run_id`` the answer is measured and nothing is recorded: there
    is no run to bind it to, and recording it unbound would let an unrelated later
    run read it. That path is still correct for a standalone producer, whose own
    entry precedes its own writes — which is the whole rule, applied to a process
    rather than a run.
    """
    try:
        environ = _env(env)
        run = safe_run_id(run_id)
        root = _root_key(project_root)

        slot = _slot_name(run, root) if run and root else None
        if slot:
            slot_value = environ.get(slot, _MISSING)
            if slot_value is not _MISSING:
                return _decode(slot_value)

        if run and environ.get(ENV_DIRTY_RUN) == run:
            recorded_root = environ.get(ENV_DIRTY_ROOT)
            # Inherit only from the exact tree. A missing root is an incomplete
            # capture, not permission to answer for every tree (external review).
            if recorded_root and root and recorded_root == root:
                return captured_dirty(run, project_root, env=environ)
    except Exception:  # noqa: BLE001 - metadata transport must never break a producer
        return None

    dirty = _measure(project_root)
    if run:
        try:
            # The keyed slot is authoritative across multiple roots. ``?`` is an
            # explicit captured-unknown marker; absence means this root was never
            # measured. The readable triple remains a compatibility/operator seam.
            if slot:
                environ[slot] = (
                    _DIRTY_UNKNOWN if dirty is None
                    else _DIRTY_TRUE if dirty else _DIRTY_FALSE
                )
            environ[ENV_DIRTY_RUN] = run
            if root:
                environ[ENV_DIRTY_ROOT] = root
            else:
                environ.pop(ENV_DIRTY_ROOT, None)
            if dirty is None:
                # Clear rather than leave a PREVIOUS run's value behind, which the
                # freshly-written run marker would otherwise make readable as this one's.
                environ.pop(ENV_DIRTY, None)
            else:
                environ[ENV_DIRTY] = _DIRTY_TRUE if dirty else _DIRTY_FALSE
        except Exception:  # noqa: BLE001 - partial transport becomes honest unknown
            # Clear only if this call installed the marker. If even cleanup fails,
            # returning unknown is still safer than leaking the exception.
            try:
                if slot:
                    environ.pop(slot, None)
                if environ.get(ENV_DIRTY_RUN) == run:
                    for name in (ENV_DIRTY, ENV_DIRTY_ROOT, ENV_DIRTY_RUN):
                        environ.pop(name, None)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
            return None
    return dirty


__all__ = [
    "ENV_DIRTY", "ENV_DIRTY_ROOT", "ENV_DIRTY_RUN", "ENV_DIRTY_SLOT_PREFIX",
    "capture_dirty", "captured_dirty",
]
