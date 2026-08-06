"""What THIS PROCESS currently holds, per lock path — the reentrancy half of
``file_lock.FileLock``.

Split out of ``file_lock`` rather than inlined there for the reason the sibling
``_host_resource_locking`` is split out of its own caller: a process-scoped
ownership registry is a self-contained concern with its own invariants, and
``file_lock`` was at its 300-line ceiling with no room to state them. The shape
here deliberately mirrors ``_host_resource_locking``'s
``_OWNER_REGISTRY_PID`` / ``_ticket_key`` pair — that module solved this exact
problem first and this one should not diverge from it by accident.

**The invariant every function below preserves:** an entry in the registry means
this process really holds the OS lock for that key, owned by the named thread.
So the entry is created only *after* the OS lock is taken, and removed *in the
same critical section* that releases it — never before, never after. A caller
that observes no entry falls through to the real OS lock and blocks, which is
the safe direction; the reverse (an entry naming a lock nobody holds) would let
a thread enter a lock that is free for someone else to take.

``file_lock_registry`` is a unique top-level module name (like ``file_lock`` and
``atomic_write``), so it imports cleanly as either ``lib.file_lock_registry`` or
``file_lock_registry``, and it imports nothing from this package.
"""
from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

__all__ = ["lock_key", "enter_reentrant", "register", "release"]


class _HeldLock:
    """One held lock path: who owns it, how deep, and the handle to release."""
    __slots__ = ("thread", "depth", "handle")

    def __init__(self, thread: int, handle) -> None:
        self.thread, self.depth, self.handle = thread, 1, handle


#: **The registry state is anchored in ``sys.modules``, not in this module.**
#: This module can legitimately be loaded more than once per process — ADR-045:
#: ``file_lock`` is imported flat by ``run_config_store`` and as ``lib.file_lock``
#: by ``record_event``, and each identity would otherwise carry its OWN ``_HELD``.
#: For a diagnostic counter that duplication is a limitation (see
#: ``durable_publish``); for a MUTEX it is a correctness bug — a nested
#: acquisition crossing the identity boundary would fail to short-circuit and
#: instead block on the OS lock it already holds, for the whole timeout. A fixed
#: private ``sys.modules`` key is the one namespace every identity shares.
_STATE_KEY = "_shipwright_file_lock_state"


def _state():
    st = sys.modules.get(_STATE_KEY)
    if st is None:
        # setdefault, not `sys.modules[k] = st`: two threads racing the first
        # call would otherwise each build a state and one would overwrite the
        # other, stranding any lock registered in the discarded one — that lock's
        # own thread would then fail to re-enter and wait out its whole timeout
        # (external code review). The dict operation is atomic, so exactly one
        # candidate wins and every caller gets the winner.
        candidate = types.ModuleType(_STATE_KEY)
        candidate.held = {}
        candidate.guard = threading.Lock()
        # A ``fork`` copies the dict but NOT the locks it describes — the child
        # holds none of them, and its main thread inherits the forking thread's
        # ident, so without a pid check the child would "re-enter" a lock it does
        # not hold and then release the PARENT's (the handles share one open file
        # description). Nothing here forks today; ``_host_resource_locking``
        # guards the same way and the two must not disagree on something this sharp.
        candidate.pid = os.getpid()
        st = sys.modules.setdefault(_STATE_KEY, candidate)
    return st


def lock_key(path: str | Path) -> str:
    """Canonical registry identity for a lock path.

    ``os.path.realpath(os.path.abspath(...))`` and NOT ``Path.resolve()``: on the
    pinned 3.11 interpreter, Windows ``resolve(strict=False)`` swallows only
    ``FileNotFoundError``, so a deny-ACL on a parent or a dead UNC share raises
    out of it — which would turn constructing a ``FileLock`` into something that
    can fail. ``realpath`` degrades to the un-resolved path instead. Same
    expression as ``_host_resource_locking._ticket_key``, deliberately.

    ``abspath`` first is what makes a *relative* lock path safe: without it two
    instances built in different working directories could share a key while
    locking different files, and the reentrant short-circuit would then skip the
    OS lock for a lock this thread does not hold.

    Never raises. ``abspath`` on a relative path calls ``os.getcwd()``, which
    fails when the cwd has been unlinked underneath the process — a live shape
    here, where iterate worktrees get removed while tools still run in them. The
    given path is a poor key but a correct fallback: it can only ever cost
    reentrancy, never exclusion, because the OS lock is still the real arbiter.
    """
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))
    except OSError:
        return os.path.normcase(str(path))


def _reset_after_fork(st) -> None:
    """Drop inherited entries when the pid changed. Caller holds the guard."""
    pid = os.getpid()
    if st.pid != pid:
        st.held.clear()
        st.pid = pid


def enter_reentrant(key: str, thread: int) -> bool:
    """Take one nesting level if ``thread`` already holds ``key``.

    ``True`` means the caller is inside a lock it already owns and must NOT
    touch the filesystem or the OS lock — not even to re-open the sidecar, which
    ``"w"`` would truncate.

    **``thread`` is a ``threading.get_ident()`` value, which the interpreter
    RECYCLES after a thread exits.** An ``__enter__`` that is never paired with
    an ``__exit__`` therefore leaves an entry naming a dead thread, and a later
    thread handed the same ident would be told it owns a lock it never took. The
    fork case above has the same shape and is guarded; this one is not, because
    the trigger is an API misuse rather than a legal operation — every
    ``__enter__`` must be paired, which ``with`` guarantees and a bare
    ``__enter__()`` call (as some tests make) does not.
    """
    st = _state()
    with st.guard:
        _reset_after_fork(st)
        held = st.held.get(key)
        if held is not None and held.thread == thread:
            held.depth += 1
            return True
    return False


def register(key: str, thread: int, handle) -> None:
    """Record a freshly-acquired OS lock. Call ONLY after acquisition succeeds."""
    st = _state()
    with st.guard:
        _reset_after_fork(st)
        st.held[key] = _HeldLock(thread, handle)


def release(key: str, thread: int, unlock) -> None:
    """Drop one nesting level; at depth 0 unlock and close, under the guard.

    ``unlock`` is passed in rather than imported so this module stays a leaf.
    It is called INSIDE the guard on purpose: releasing outside it would let a
    new acquirer take the OS lock while the entry still named the old owner.
    Neither ``unlock`` nor ``close`` re-enters this module, so holding the guard
    across them cannot deadlock.
    """
    st = _state()
    with st.guard:
        # The fork guard belongs HERE too, and its absence was the sharpest hole
        # in this module (external code review, high): a forked child inherits
        # both the entry and the forking thread's ident, so without this its exit
        # would look like the owner and would unlock + close a handle that shares
        # an open file description with the PARENT — releasing a lock the parent
        # still believes it holds. Guarding only the acquire paths guards nothing.
        _reset_after_fork(st)
        held = st.held.get(key)
        if held is None or held.thread != thread:
            return
        held.depth -= 1
        if held.depth > 0:
            return
        del st.held[key]
        unlock(held.handle)
        held.handle.close()
