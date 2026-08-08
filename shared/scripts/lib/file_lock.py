"""Cross-platform advisory file locks for Shipwright helpers.

This module hosts TWO complementary primitives that share the same
``*.lock``-sidecar + ``fcntl.flock`` (POSIX) / ``msvcrt.locking`` (Windows)
mechanism, and — since ``trg-dc013d82`` — one bounded acquisition loop.
Neither needs the target file itself to be open, so the lock file is
independent of the write path — which keeps atomic-rename writes simple.

``file_lock`` (context-manager function) — timeout variant
----------------------------------------------------------
Used by ``append_changelog_entry.py`` and ``append_phase_history.py`` so
concurrent callers (heartbeat tick + phase-complete hook, for example)
can't lost-update each other when appending to ``CHANGELOG.md`` or
``shipwright_run_config.json``.

Timeout is hard (no silent retry loop): if the lock can't be acquired within
``timeout_seconds`` it raises ``LockTimeout``. Callers should surface that as a
non-zero exit code rather than silently dropping the write.

``FileLock`` (class) — bounded-wait, same-thread-reentrant variant
------------------------------------------------------------------
Used by the JSONL append-log writers ``tools/record_event.py`` and
``triage.py``, and — since ``trg-2e961fee`` — ``phase_task_lifecycle.
_PhaseTasksLock``, itself a third literal copy of this mechanism until
delegated. All guard short critical sections and want to serialize rather
than fail, so this waits — but no longer waits *forever*. The
near-identical class was copied between the first two; it now lives here
once (iterate-2026-06-13-shc-file-lock). ``__enter__`` creates the lock
file's parent directory (``parents=True, exist_ok=True``) so a first-ever
append into a not-yet-created ``.shipwright/`` directory does not raise.

**It used to have neither a bound nor reentrancy** (``trg-dc013d82``, finding
24): POSIX ``flock(LOCK_EX)`` blocked indefinitely, Windows spun a 1 ms loop
forever, and a nested acquisition waited on a lock only the waiting thread could
release — a self-deadlock with no diagnostic. That lock sits on hook paths and on
``setup_iterate_worktree`` step 5, exactly where a silent hang cannot be told
apart from a session death. No double acquisition exists in the code today:
reentrancy is a guardrail, the bound is the live repair.
"""

from __future__ import annotations

import errno
import math
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:  # loaded as ``lib.file_lock``
    from .file_lock_registry import enter_reentrant, lock_key, register, release
except ImportError:  # loaded as top-level ``file_lock`` (lib/ is on sys.path)
    from file_lock_registry import enter_reentrant, lock_key, register, release

#: How long a :class:`FileLock` waits before giving up. Deliberately NOT the
#: sister's 5 s, and derived rather than picked: that one guards a single short
#: append, while this lock's longest legitimate holder is the ``sweep_outbox``
#: triage sweep — ~225 s if every git call in its critical section runs to its
#: own timeout (full inventory in the iterate spec). 600 s clears that worst
#: *bounded* hold by ~2.7×. It is not tuned for responsiveness and cannot be:
#: the only job of this bound is to turn an unbounded hang into a diagnosable
#: failure. Pass a tighter value if you know your own hold is short.
FILE_LOCK_DEFAULT_TIMEOUT_SECONDS = 600.0

#: Poll backoff. Starts at the 1 ms the Windows branch historically used, so an
#: almost-free lock is still acquired promptly, and doubles to a ceiling — which
#: is what stops the busy-spin a flat 1 ms poll would sustain for a whole budget.
#: NOTE this also changed POSIX: :class:`FileLock` used to block in the kernel on
#: ``flock(LOCK_EX)`` and now polls, losing that call's rough queueing fairness
#: and adding up to one ceiling of handoff latency. Accepted (sub-second holds),
#: but it is why a waiter can in principle be starved under sustained contention.
_ACQUIRE_INITIAL_SLEEP_SECONDS = 0.001
_ACQUIRE_MAX_SLEEP_SECONDS = 0.05

#: Windows errnos meaning "another handle holds this range", not a fault.
#: EDEADLOCK is included because ``msvcrt.locking`` documents it for the retry
#: path though ``LK_NBLCK`` measured EACCES; spellings looked up defensively.
_CONTENTION_ERRNOS = frozenset(
    v for v in (getattr(errno, n, None) for n in ("EACCES", "EDEADLOCK", "EDEADLK"))
    if v is not None
)


class LockTimeout(RuntimeError):
    """Raised when a file lock cannot be acquired within the timeout."""


def _validated_timeout(timeout_seconds) -> float | None:
    """``None`` or a finite, non-negative number of seconds — or ``ValueError``.

    ``NaN`` is the one that matters: every deadline comparison against it is
    ``False``, so it would silently restore the unbounded wait without any caller
    passing ``None`` to ask for it. ``bool`` is rejected explicitly because it is
    an ``int`` subclass and ``timeout_seconds=True`` is far likelier a mistake.
    """
    if timeout_seconds is None:
        return None
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError(f"timeout_seconds must be None or a number, got {timeout_seconds!r}")
    value = float(timeout_seconds)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"timeout_seconds must be finite and >= 0, got {timeout_seconds!r}")
    return value


def _try_acquire_once(fh) -> bool:
    """One non-blocking attempt. ``True`` on success, ``False`` if held."""
    if sys.platform == "win32":
        import msvcrt  # type: ignore[import-not-found]

        try:
            # Lock a single byte at offset 0. msvcrt locks the range at the
            # CURRENT position, so seek to 0 first — else an "a+" handle on a
            # non-empty lock file locks a different offset than peers locking
            # byte 0 (phase_task_lifecycle._PhaseTasksLock) and the two fail to
            # mutually exclude. Mirrors _release.
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError as exc:
            # Only "someone holds it". Measured on Windows 11: contention is
            # PermissionError/EACCES, a real fault (EBADF, dead share) a plain
            # OSError — neither carries a winerror, so the TYPE is the signal.
            # Swallowing every OSError made a fault spin the whole budget then
            # blame a contender that never existed (doubt review).
            if exc.errno in _CONTENTION_ERRNOS:
                return False
            raise
    import fcntl  # type: ignore[import-not-found]

    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        # Only "someone holds it" — a real error (EBADF, …) still propagates.
        return False


def _acquire_bounded(fh, timeout_seconds: float | None, path: str,
                     max_sleep: float = _ACQUIRE_MAX_SLEEP_SECONDS) -> None:
    """Poll until acquired, or raise :class:`LockTimeout` at the deadline.

    ``timeout_seconds=0`` is exactly one attempt; ``None`` polls forever. The
    deadline is monotonic, so a clock adjustment cannot shorten or extend a wait,
    and each sleep is clamped to the remaining budget so the final attempt lands
    *at* the deadline rather than past it. Both primitives in this
    module share this loop; they used to have one each — the class's unbounded,
    the function's a flat spin — which is how one got a bound and the other not.
    """
    started = time.monotonic()
    deadline = None if timeout_seconds is None else started + timeout_seconds
    delay = _ACQUIRE_INITIAL_SLEEP_SECONDS
    while True:
        if _try_acquire_once(fh):
            return
        if deadline is None:
            time.sleep(delay)
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LockTimeout(
                    f"could not acquire {path} within {timeout_seconds}s "
                    f"(waited {time.monotonic() - started:.1f}s)")
            time.sleep(min(delay, remaining))
        delay = min(delay * 2, max_sleep)


def _release(fh) -> None:
    if sys.platform == "win32":
        try:
            import msvcrt  # type: ignore[import-not-found]
            # Seek back to 0 — msvcrt.locking unlocks at the current position.
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        try:
            import fcntl  # type: ignore[import-not-found]
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


@contextmanager
def file_lock(
    lock_path: str | os.PathLike[str],
    *,
    timeout_seconds: float = 5.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Acquire an advisory exclusive lock on ``lock_path``.

    The lock file is created if missing and left behind on disk; this is
    intentional — the file is cheap and having it on disk avoids a TOCTOU race
    between "check exists" and "acquire". Release happens on context-manager
    exit.

    ``poll_interval`` is now the backoff *ceiling*: the wait starts at 1 ms and
    doubles up to it, where it used to be a flat interval that made every
    almost-free acquisition pay the full 50 ms. Timeout and exception unchanged;
    ``timeout_seconds=None`` now means unbounded here too (it used to TypeError),
    while ``NaN``/``inf``/negative are rejected rather than spinning forever.
    """
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append mode: creates the file if missing without truncating its content.
    fh = open(path, "a+", encoding="utf-8")
    try:
        _acquire_bounded(fh, _validated_timeout(timeout_seconds), str(path),
                         max_sleep=poll_interval)
        try:
            yield
        finally:
            _release(fh)
    finally:
        fh.close()


class FileLock:
    """Cross-platform mutex via a dedicated ``.lock`` sidecar file.

    Used by the JSONL append-log writers in ``tools/record_event.py`` and
    ``triage.py``. ``msvcrt.locking`` on Windows is unreliable in append mode, so
    a dedicated lock file is used for mutual exclusion on all platforms.

    Waits up to ``timeout_seconds`` (default
    :data:`FILE_LOCK_DEFAULT_TIMEOUT_SECONDS`) and then raises
    :class:`LockTimeout` naming the lock and the wait — a caller that hangs is
    indistinguishable from a dead session, one that raises is not. ``0`` is a
    single non-blocking attempt; ``None`` restores the historical unbounded
    block for a caller that genuinely wants it. Re-acquiring a path the **same
    thread** already holds nests: it enters immediately, and the lock is released
    only when the outermost block exits. Another thread is excluded throughout.

    **One instance belongs to one thread.** Reentrancy is keyed on the PATH, so
    two instances on one call stack is supported; SHARING an instance between
    threads is not — ``_entries`` is a plain instance counter while the depth
    lives in the registry, so a lost update would strand the entry (doubt review).

    ``__enter__`` first creates the lock file's parent directory
    (``parents=True, exist_ok=True``) so a first-ever append into a
    not-yet-created ``.shipwright/`` directory does not raise — the strict
    superset behaviour the two former call-site copies are unified on.
    """

    def __init__(self, lock_path: str | Path, *,
                 timeout_seconds: float | None = FILE_LOCK_DEFAULT_TIMEOUT_SECONDS):
        # Absolutised ONCE, and used for both the registry key and the open()
        # below, so the identity and the file actually locked can never come
        # from two different working directories. The caller's original spelling
        # is kept only for diagnostics, so a LockTimeout names the lock it asked
        # for rather than a resolved path it may not recognise.
        self._given_path = str(lock_path)
        self._lock_path = Path(os.path.abspath(lock_path))
        self._timeout_seconds = _validated_timeout(timeout_seconds)
        self._key = lock_key(self._lock_path)
        # How many registry increments THIS instance made — ownership is never
        # inferred. Makes __exit__ after a failed __enter__, a double __exit__
        # and a re-used instance all safe.
        self._entries = 0
        self._fp = None

    def __enter__(self):
        ident = threading.get_ident()
        if enter_reentrant(self._key, ident):
            self._entries += 1
            return self
        # Only a NON-reentrant acquisition touches the filesystem: a nested one
        # must not re-create the parent or re-open (and so re-truncate) the
        # sidecar it already holds.
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        fp = open(self._lock_path, "w", encoding="utf-8")
        try:
            _acquire_bounded(fp, self._timeout_seconds, self._given_path)
        except BaseException:
            # An unsuccessful acquisition closes the handle it opened and leaves
            # the instance un-entered: a timeout must not leak a descriptor or
            # leave an instance looking acquired.
            fp.close()
            raise
        # Registry FIRST, instance state second, and do not "tidy" that order:
        # reversed, an async exception between the two would leave an instance
        # believing it holds a lock the registry never recorded, and __exit__
        # would then release someone else's. This way round the same interrupt
        # strands the lock instead — bad, but bounded and never a broken mutex.
        register(self._key, ident, fp)
        self._fp = fp
        self._entries += 1
        return self

    def __exit__(self, *exc):
        if self._entries <= 0:
            return
        self._entries -= 1
        release(self._key, threading.get_ident(), _release)
        self._fp = None
