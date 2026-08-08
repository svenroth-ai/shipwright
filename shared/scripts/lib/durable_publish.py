"""The platform half of publishing an atomically-written file.

``atomic_write.durable_atomic_write`` owns the *sequence* — temp file, fsync,
``os.replace``, directory fsync. This leaf owns the two things that sequence has
to know about the operating system, and that are otherwise easy to get subtly
wrong in the middle of it:

* which Windows error codes mean *someone else has the destination open*, and
* what mode the published file must carry on POSIX.

It lives beside ``atomic_write`` rather than inside it because that module sits
at the repo's 300-line source limit; a change to either of the two facts above
has nowhere to be written down there. Nothing was relocated here that
``trg-dc013d82`` was not already editing.

``durable_publish`` is a unique top-level module name (like ``atomic_write`` and
``file_lock``), so it imports cleanly both as ``lib.durable_publish`` and as
``durable_publish``. It has no intra-package imports of its own — deliberately,
so it stays loadable by either route without dragging a ``lib`` namespace along.

One consequence, stated because it is easy to trip over: ``atomic_write`` is
genuinely imported BOTH ways in this repo, so a single process can hold two
copies of this module and therefore two :func:`mode_carry_failures` counters. A
reader that reaches one will not see refusals recorded through the other. The
counter is a diagnostic, not a gate, so this is a limitation rather than a bug —
but do not build anything on the count being process-global.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

__all__ = ["SHARING_VIOLATION_WINERRORS", "carry_destination_mode",
           "mode_carry_failures", "reset_mode_carry_failures"]

#: Windows codes seen when someone else has the destination open. Measured on
#: Windows 11: a plain reader, a memory-mapped holder (what AV/indexers do) and
#: a byte-range lock ALL surface as ``PermissionError`` winerror 5; 32
#: (``ERROR_SHARING_VIOLATION``) is kept because it is documented for this path.
#:
#: **33 is defence in depth, not a measured fix — say so plainly.** CPython's
#: ``PC/errmap.h`` maps ``ERROR_LOCK_VIOLATION`` to ``EACCES`` and so to
#: ``PermissionError`` exactly like 5 and 32, so a host that reports it would
#: fall straight out of the retry. But it has now been probed TWICE on Windows 11
#: local NTFS — during iterate-2026-07-27-run-unit-parallel-race, which declined
#: it on that evidence, and again for ``trg-dc013d82`` finding 10 — and both
#: times a byte-range-locked destination gave **5**, because holding a byte range
#: also requires holding the file open and the open handle alone already yields 5.
#: It is included anyway because the cost is bounded and already accepted for the
#: far more ambiguous 5 (at worst the same short stall), while the payoff on a
#: host or filesystem that does report 33 is a write not silently lost.
#:
#: **What the same probe DID measure is not a code number at all.** A read of a
#: byte-range-locked region fails inside the read syscall, not ``CreateFile``, so
#: CPython raises an errno-only ``PermissionError`` with ``winerror`` **None** —
#: which no set of codes can ever match. This module's set stays winerror-only
#: (the write path never retries a ``None`` winerror — a different, real failure
#: there); the read side's opt-in retry lives in
#: ``atomic_write._retry_past_sharing_violations``'s ``retry_none_winerror``
#: flag instead (``trg-db1de213``, fixed after this run deliberately deferred
#: it — the decision to stall a genuinely denied read for the full read budget
#: needed its own reasoning, not to ride along with three unrelated findings).
#:
#: **5 is ambiguous and we cannot fix that.** ``ERROR_ACCESS_DENIED`` is equally
#: what a read-only destination, a deny-ACL, or a destination that is a
#: directory returns (all three measured). Those stall for the caller's retry
#: budget before failing. Accepted knowingly: a bounded stall that still fails
#: loudly beats silently losing a write, and the two are indistinguishable at
#: this layer.
SHARING_VIOLATION_WINERRORS = frozenset({5, 32, 33})

#: Times this process could not carry a destination's mode onto its replacement.
#: A counter and not a ``warnings.warn`` for the reason the sibling retry counter
#: gives (``trg-0a294ef3``): a warning has no consumer and is globally
#: suppressible, while a counter is something a test can assert on. It exists at
#: all because a silently narrowed mode is a security-posture change, not a
#: cosmetic one.
_failure_count = 0
_failure_lock = threading.Lock()


def mode_carry_failures() -> int:
    """Failed mode carries so far in this process."""
    with _failure_lock:
        return _failure_count


def reset_mode_carry_failures() -> None:
    """Zero the counter — for tests that need a clean baseline."""
    global _failure_count
    with _failure_lock:
        _failure_count = 0


def _note_failure() -> None:
    global _failure_count
    with _failure_lock:
        _failure_count += 1


def carry_destination_mode(fd: int, dest: Path | str) -> bool:
    """Give the open temp file ``fd`` the mode ``dest`` currently has.

    Returns ``True`` when a mode was carried, ``False`` when there was none to
    carry or the attempt was refused. **Never raises for an OS-level refusal**:
    losing a mode must not cost the caller its write.

    Why this exists: ``tempfile.mkstemp`` creates its file ``0600`` by design and
    ``os.replace`` publishes the *source* inode — mode included — so a rewrite
    through the atomic-write primitive silently replaced an existing file's
    permissions with ``0600``. On POSIX that strips group and other access from
    every file written this way, and git records nothing (only the x-bit is
    tracked), so the loss is invisible in review and in history.

    Why it takes a **descriptor** and not the temp path: the caller must apply
    the mode while the file is still open and *before* its ``fsync``, so the one
    fsync that makes the bytes durable covers the metadata change too. Doing it
    after the fsync would leave the mode resting on the best-effort
    parent-directory fsync, which does not cover the inode — weakening the very
    guarantee the primitive exists to provide.

    A destination that does not exist yet has no mode to carry, and the
    replacement is deliberately left at ``mkstemp``'s ``0600`` rather than being
    given a guessed one: the "natural" mode of a new file is ``0666 & ~umask``,
    and ``os.umask`` can only be READ by temporarily SETTING it — a
    process-global mutation with a window in which every other thread's file
    creation gets the wrong mode. A shared primitive must not make that trade on
    a caller's behalf. That case is not counted as a failure.

    The platform test is ``os.name != "nt"`` AND ``hasattr(os, "fchmod")``. The
    capability half keeps the Windows branch reachable from a POSIX test host by
    removing the attribute; the ``os.name`` half is what stops the carry from
    switching itself ON if a future CPython grows ``os.fchmod`` on Windows, where
    ``st_mode`` is a read-only-attribute proxy (0o444/0o666) rather than a POSIX
    mode. Carrying that would publish read-only files, and the NEXT ``os.replace``
    onto one fails with winerror 5 — which IS in the sharing-violation set, so it
    would be retried for the whole budget and then re-raised: a permanently
    unwritable destination wearing a transient-contention costume.
    """
    if os.name == "nt" or not hasattr(os, "fchmod"):
        return False
    try:
        mode = os.stat(dest).st_mode & 0o7777
    except FileNotFoundError:
        return False
    except OSError:
        _note_failure()
        return False
    try:
        os.fchmod(fd, mode)
    except OSError:
        _note_failure()
        return False
    return True
