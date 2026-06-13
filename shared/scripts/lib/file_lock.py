"""Cross-platform advisory file locks for Shipwright helpers.

This module hosts TWO complementary primitives that share the same
``*.lock``-sidecar + ``fcntl.flock`` (POSIX) / ``msvcrt.locking`` (Windows)
mechanism. Neither needs the target file itself to be open, so the lock file
is independent of the write path — which keeps atomic-rename writes simple.

``file_lock`` (context-manager function) — timeout variant
----------------------------------------------------------
Used by ``append_changelog_entry.py`` and ``append_phase_history.py`` so
concurrent callers (heartbeat tick + phase-complete hook, for example)
can't lost-update each other when appending to ``CHANGELOG.md`` or
``shipwright_run_config.json``.

Timeout is hard (no silent retry loop): if the lock can't be acquired
within ``timeout_seconds`` the context manager raises ``LockTimeout``.
Callers should surface that as a non-zero exit code so the caller knows
to investigate rather than silently drop the write.

``FileLock`` (class) — block-until-acquired variant
---------------------------------------------------
Used by the JSONL append-log writers ``tools/record_event.py`` and
``triage.py`` (and the triage sweep / GC / reconcile helpers that share the
canonical triage lock). It blocks until the lock is acquired (no timeout) —
the appends it guards are short and the writers want to serialize rather than
fail. The near-identical class was copied between those two modules; it now
lives here once and both ``import FileLock as _FileLock``
(iterate-2026-06-13-shc-file-lock). ``__enter__`` creates the lock file's
parent directory (``parents=True, exist_ok=True``) so a first-ever append into
a not-yet-created ``.shipwright/`` directory does not raise.
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class LockTimeout(RuntimeError):
    """Raised when a file lock cannot be acquired within the timeout."""


@contextmanager
def file_lock(
    lock_path: str | os.PathLike[str],
    *,
    timeout_seconds: float = 5.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Acquire an advisory exclusive lock on ``lock_path``.

    The lock file is created if missing and left behind on disk; this is
    intentional — the file is cheap and having it on disk avoids a TOCTOU
    race between "check exists" and "acquire". The lock release happens
    automatically when the context manager exits.
    """
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Open in append mode so the file is created if missing without
    # truncating any existing content.
    fh = open(path, "a+", encoding="utf-8")
    try:
        deadline = time.monotonic() + timeout_seconds
        if sys.platform == "win32":
            _acquire_windows(fh, deadline, poll_interval, str(path))
        else:
            _acquire_posix(fh, deadline, poll_interval, str(path))
        try:
            yield
        finally:
            _release(fh)
    finally:
        fh.close()


def _acquire_posix(fh, deadline: float, poll_interval: float, path: str) -> None:
    import fcntl  # type: ignore[import-not-found]

    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise LockTimeout(f"could not acquire {path} within deadline")
            time.sleep(poll_interval)


def _acquire_windows(fh, deadline: float, poll_interval: float, path: str) -> None:
    import msvcrt  # type: ignore[import-not-found]

    while True:
        try:
            # Lock a single byte at offset 0. msvcrt locks the byte range at
            # the CURRENT position, so seek to 0 first — otherwise an "a+"
            # handle on a non-empty lock file would lock a different offset
            # than peers locking byte 0 (e.g. phase_task_lifecycle._PhaseTasksLock)
            # and the locks would fail to mutually exclude. Mirrors _release.
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise LockTimeout(f"could not acquire {path} within deadline")
            time.sleep(poll_interval)


def _release(fh) -> None:
    if sys.platform == "win32":
        try:
            import msvcrt  # type: ignore[import-not-found]

            # Seek back to 0 before unlock — msvcrt.locking unlocks the
            # range at the current file position.
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


class FileLock:
    """Cross-platform mutex via a dedicated ``.lock`` sidecar file.

    Block-until-acquired variant (no timeout): used by the JSONL append-log
    writers in ``tools/record_event.py`` and ``triage.py``. ``msvcrt.locking``
    on Windows is unreliable in append mode, so a dedicated lock file is used
    for mutual exclusion on all platforms.

    ``__enter__`` first creates the lock file's parent directory
    (``parents=True, exist_ok=True``) so a first-ever append into a
    not-yet-created ``.shipwright/`` directory does not raise — this is the
    strict superset behaviour the two former call-site copies are unified on
    (iterate-2026-06-13-shc-file-lock).
    """

    def __init__(self, lock_path: str | Path):
        self._lock_path = Path(lock_path)
        self._fp = None

    def __enter__(self):
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self._lock_path, "w", encoding="utf-8")
        if sys.platform == "win32":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.001)
        else:
            import fcntl
            fcntl.flock(self._fp, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fp:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    try:
                        msvcrt.locking(self._fp.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl
                    fcntl.flock(self._fp, fcntl.LOCK_UN)
                self._fp.close()
            finally:
                # Reset so a re-used instance / double-__exit__ never acts on a
                # stale closed handle (external code review, OpenAI-medium). The
                # locking behaviour is unchanged — __enter__ always reopens.
                self._fp = None
