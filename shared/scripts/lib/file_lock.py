"""Cross-platform advisory file lock for Shipwright helpers.

Used by ``append_changelog_entry.py`` and ``append_phase_history.py`` so
concurrent callers (heartbeat tick + phase-complete hook, for example)
can't lost-update each other when appending to ``CHANGELOG.md`` or
``shipwright_run_config.json``.

The POSIX backend uses ``fcntl.flock`` on a dedicated ``*.lock`` file;
the Windows backend uses ``msvcrt.locking``. Neither needs the target
file itself to be open, so the lock file is independent of the write
path — which keeps atomic-rename writes simple.

Timeout is hard (no silent retry loop): if the lock can't be acquired
within ``timeout_seconds`` the context manager raises ``LockTimeout``.
Callers should surface that as a non-zero exit code so the caller knows
to investigate rather than silently drop the write.
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
            # Lock a single byte at offset 0. msvcrt only locks byte ranges,
            # but that's enough for an advisory coordination primitive.
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
