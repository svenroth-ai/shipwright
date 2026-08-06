"""Tests for ``lib.file_lock_registry`` — the reentrancy half of ``FileLock``.

Split out of ``file_lock`` during trg-dc013d82 so the registry's invariants had
somewhere to be stated. These pin the two properties that are load-bearing for
mutual exclusion rather than merely for convenience:

* the key must not depend on the working directory, or two instances built from
  the same relative path in different directories would share an identity while
  locking DIFFERENT files — and the reentrant short-circuit would then skip the
  OS lock for a lock the thread does not hold;
* the key function must not raise, because it runs in ``FileLock.__init__``,
  which callers are entitled to treat as infallible.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import file_lock_registry as reg  # noqa: E402


def _no_unlock(handle):
    """Release hook that unlocks nothing — these tests register fake handles.

    Module-level rather than an inline ``lambda h: None``: a lambda's implicit
    return sitting inside a ``finally`` block is flagged as a return-from-finally
    (CodeQL py/exit-from-finally), the pattern that silently swallows exceptions.
    """


def test_key_is_independent_of_the_working_directory(tmp_path, monkeypatch):
    """A relative path yields the SAME key from any cwd — exclusion depends on it."""
    target = tmp_path / "sub" / "a.lock"
    target.parent.mkdir(parents=True)
    target.touch()

    monkeypatch.chdir(tmp_path)
    from_parent = reg.lock_key("sub/a.lock")
    monkeypatch.chdir(tmp_path / "sub")
    from_child = reg.lock_key("a.lock")

    assert from_parent == from_child == reg.lock_key(target)


def test_key_does_not_raise_on_an_unresolvable_path(tmp_path):
    """``FileLock.__init__`` must stay infallible.

    ``Path.resolve()`` on the pinned 3.11 interpreter can raise on Windows for a
    path whose parent cannot be queried; ``realpath`` degrades to the
    un-resolved path instead. A missing path is the portable stand-in for that
    shape — the contract is "returns a string, never raises".
    """
    key = reg.lock_key(tmp_path / "does" / "not" / "exist.lock")
    assert isinstance(key, str) and key


def test_a_second_thread_is_not_treated_as_the_owner(tmp_path):
    """Reentrancy is per-THREAD, not per-process — the whole point of the ident."""
    key = reg.lock_key(tmp_path / "owned.lock")
    handle_closed: list[bool] = []

    class _Handle:
        def close(self):
            handle_closed.append(True)

    reg.register(key, threading.get_ident(), _Handle())
    try:
        assert reg.enter_reentrant(key, threading.get_ident()) is True
        # …and release that extra level again so the teardown below is at depth 1.
        reg.release(key, threading.get_ident(), _no_unlock)

        seen: list[bool] = []
        other = threading.Thread(
            target=lambda: seen.append(reg.enter_reentrant(key, threading.get_ident())))
        other.start()
        other.join(timeout=5)
        assert not other.is_alive()
        assert seen == [False], "another thread must never inherit ownership"
    finally:
        reg.release(key, threading.get_ident(), _no_unlock)

    assert handle_closed == [True], "the outermost release must close the handle"
    assert reg.enter_reentrant(key, threading.get_ident()) is False


def test_release_by_a_non_owner_is_a_noop(tmp_path):
    """A stray release must not free a lock another thread holds."""
    key = reg.lock_key(tmp_path / "stray.lock")
    unlocked: list[bool] = []

    class _Handle:
        def close(self):
            unlocked.append(True)

    reg.register(key, threading.get_ident(), _Handle())
    try:
        done: list[bool] = []
        other = threading.Thread(
            target=lambda: (reg.release(key, threading.get_ident(), _no_unlock),
                            done.append(True)))
        other.start()
        other.join(timeout=5)
        assert done == [True]
        assert unlocked == [], "a non-owner release must not close the owner's handle"
        assert reg.enter_reentrant(key, threading.get_ident()) is True
        reg.release(key, threading.get_ident(), _no_unlock)
    finally:
        reg.release(key, threading.get_ident(), _no_unlock)


def test_a_forked_child_does_not_inherit_ownership(tmp_path, monkeypatch):
    """A fork copies the registry but NOT the locks it describes.

    Without the pid guard the child's main thread — which inherits the forking
    thread's ident — would "re-enter" a lock it does not hold, and its exit would
    release the PARENT's (the handles share one open file description). Simulated
    by moving ``os.getpid`` rather than actually forking, so the check runs on
    Windows too, where ``os.fork`` does not exist at all.
    """
    key = reg.lock_key(tmp_path / "forked.lock")
    reg.register(key, threading.get_ident(), object())

    # Patch the module reference, not os.getpid itself: `reg.os` IS the real
    # module, so stubbing on it is process-global AND makes the stub recurse into
    # itself when it calls os.getpid() to compute the fake value.
    child_pid = os.getpid() + 1

    class _ChildOs:
        def __getattr__(self, name):
            return getattr(os, name)

    child_os = _ChildOs()
    child_os.getpid = lambda: child_pid
    monkeypatch.setattr(reg, "os", child_os)

    assert reg.enter_reentrant(key, threading.get_ident()) is False, (
        "the child must not believe it owns a lock only the parent holds")


def test_a_forked_child_does_not_release_the_parents_lock(tmp_path, monkeypatch):
    """The other half of the fork guard, and the one that was missing.

    Guarding only the ACQUIRE paths guards nothing: a forked child inherits both
    the registry entry and the forking thread's ident, so its ``__exit__`` would
    match as the owner and unlock + close a handle that shares an open file
    description with the parent — dropping a lock the parent still believes it
    holds. Found by external code review after the acquire-side guard had already
    been added and reviewed twice.
    """
    key = reg.lock_key(tmp_path / "forked-release.lock")
    released: list[str] = []

    class _Handle:
        def close(self):
            released.append("closed")

    reg.register(key, threading.get_ident(), _Handle())

    child_pid = os.getpid() + 1

    class _ChildOs:
        def __getattr__(self, name):
            return getattr(os, name)

    child_os = _ChildOs()
    child_os.getpid = lambda: child_pid
    monkeypatch.setattr(reg, "os", child_os)

    reg.release(key, threading.get_ident(), lambda h: released.append("unlocked"))
    assert released == [], "the child released a lock only the parent holds"
