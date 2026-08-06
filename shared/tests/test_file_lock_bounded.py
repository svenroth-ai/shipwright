"""``FileLock``'s bounded wait and same-thread reentrancy (trg-dc013d82, finding 24).

Split out of ``test_file_lock.py`` to keep both inside the 300-line budget — the
same shape as ``test_atomic_write`` / ``test_atomic_write_windows_retry``. That
file keeps the four tests pinning the ORIGINAL extraction (mutual exclusion,
parent-dir creation, reuse, call-site aliasing); this one covers what the bound
and the reentrancy added.

The class used to block forever in both platform branches, so a contended lock
was indistinguishable from a dead session and a nested acquisition deadlocked
against itself with no diagnostic. Every test here is written so a REGRESSION
FAILS rather than wedging the suite: each uses its own tmp_path, an explicit
short timeout, event synchronisation, release in ``finally``, and a bounded
``join`` — a daemon thread parked on the 600 s default would otherwise poison
later tests (external plan review).
"""
from __future__ import annotations

import contextlib
import sys
import threading
import time
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.file_lock import FileLock, LockTimeout  # noqa: E402


@contextlib.contextmanager
def _held_by_another_thread(lock_path):
    """Hold ``lock_path`` on a worker thread for the duration of the block."""
    holding = threading.Event()
    release = threading.Event()

    def hold():
        with FileLock(lock_path, timeout_seconds=10):
            holding.set()
            release.wait(timeout=10)

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert holding.wait(timeout=10), "holder thread never acquired the lock"
        yield
    finally:
        release.set()
        worker.join(timeout=10)
        assert not worker.is_alive(), "holder thread never exited"


def _acquire_from_another_thread(lock_path, timeout_seconds):
    """Attempt an acquisition off-thread; return ``"acquired"`` or ``"timeout"``."""
    outcome: list[str] = []

    def run():
        try:
            with FileLock(lock_path, timeout_seconds=timeout_seconds):
                outcome.append("acquired")
        except LockTimeout:
            outcome.append("timeout")

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "acquisition attempt never returned — still blocking"
    return outcome[0]


def test_timeout_raises_instead_of_blocking_forever(tmp_path):
    """AC-5: a contended lock gives up at the deadline and says which lock.

    The whole point of the bound: on a hook path a silent hang cannot be told
    apart from a session death, so it must terminate with a diagnostic.
    """
    lock_path = tmp_path / "bounded.lock"
    with _held_by_another_thread(lock_path):
        started = time.monotonic()
        with pytest.raises(LockTimeout) as excinfo:
            with FileLock(lock_path, timeout_seconds=0.2):
                pass  # pragma: no cover — acquisition must not succeed
        waited = time.monotonic() - started

    assert 0.15 <= waited < 5.0, f"gave up after {waited}s, expected ~0.2s"
    message = str(excinfo.value)
    assert str(lock_path) in message, "the message must name WHICH lock"
    assert "waited" in message, "…and how long it waited — a bare timeout is not a diagnosis"


def test_zero_timeout_is_one_non_blocking_attempt(tmp_path, monkeypatch):
    """AC-7: ``timeout_seconds=0`` tries EXACTLY once and fails fast.

    Counts the attempts rather than timing them: a fast failure is also what 100
    attempts against a held lock looks like, so elapsed time alone cannot tell
    "one attempt" from "many" (doubt review).
    """
    import lib.file_lock as fl  # noqa: PLC0415

    lock_path = tmp_path / "nonblocking.lock"
    attempts: list[int] = []
    real_try = fl._try_acquire_once
    monkeypatch.setattr(fl, "_try_acquire_once",
                        lambda fh: (attempts.append(1), real_try(fh))[1])

    with _held_by_another_thread(lock_path):
        # The holder's OWN successful acquisition goes through the same spy —
        # count only what the zero-timeout attempt below does.
        attempts.clear()
        with pytest.raises(LockTimeout):
            with FileLock(lock_path, timeout_seconds=0):
                pass  # pragma: no cover
    assert len(attempts) == 1, f"expected exactly one attempt, made {len(attempts)}"


def test_none_timeout_restores_the_unbounded_block(tmp_path):
    """AC-7: the historical forever-block survives, reachable only on request."""
    lock_path = tmp_path / "unbounded.lock"
    holding = threading.Event()

    def hold_briefly():
        with FileLock(lock_path, timeout_seconds=10):
            holding.set()
            time.sleep(0.3)

    worker = threading.Thread(target=hold_briefly)
    worker.start()
    try:
        assert holding.wait(timeout=10)
        started = time.monotonic()
        with FileLock(lock_path, timeout_seconds=None):
            waited = time.monotonic() - started
    finally:
        worker.join(timeout=10)
        assert not worker.is_alive()

    assert waited >= 0.2, "an unbounded acquirer must have waited for the holder"
    # Timing alone cannot tell None from a finite default — a 600 s budget would
    # also have waited 0.3 s and succeeded. Pin the state that makes it unbounded
    # (doubt review: this test used to claim more than it proved).
    assert FileLock(lock_path, timeout_seconds=None)._timeout_seconds is None


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "5"])
def test_invalid_timeout_is_rejected(tmp_path, bad):
    """``NaN`` is the sharp one: every deadline comparison against it is False,
    so it would silently recreate an unbounded wait without anyone asking for
    one (external plan review, openai)."""
    with pytest.raises(ValueError):
        FileLock(tmp_path / "bad.lock", timeout_seconds=bad)


def test_a_real_fault_propagates_instead_of_being_polled(tmp_path):
    """A fault is not contention, and must not be waited out.

    Both branches used to differ here: POSIX narrowed to ``BlockingIOError``
    while Windows swallowed every ``OSError``, so a non-transient failure (a dead
    network share) polled for the whole budget and then blamed a contender that
    never existed. A dead descriptor is the portable stand-in — ``EBADF`` on
    either platform — and it must come straight back out.
    """
    import lib.file_lock as fl  # noqa: PLC0415

    probe = open(tmp_path / "dead.lock", "w", encoding="utf-8")
    dead_fd = probe.fileno()
    probe.close()

    class _DeadHandle:
        def seek(self, *a):
            pass

        def fileno(self):
            return dead_fd

    started = time.monotonic()
    with pytest.raises(OSError):
        fl._try_acquire_once(_DeadHandle())
    assert time.monotonic() - started < 1.0, "a fault must not be polled at all"


def test_same_thread_reentry_enters_immediately_and_holds_until_outermost_exit(tmp_path):
    """AC-6: nested acquisition succeeds, and exclusion survives the inner exit.

    Two DIFFERENT instances on one call stack — the shape the card describes
    (``record_event`` inside a sweep), which a per-instance flag would miss.
    """
    lock_path = tmp_path / "reentrant.lock"
    outer = FileLock(lock_path, timeout_seconds=1)
    inner = FileLock(lock_path, timeout_seconds=1)

    with outer:
        with inner:
            assert _acquire_from_another_thread(lock_path, 0.05) == "timeout"
        # Inner released: the lock must STILL be held by the outer block.
        assert _acquire_from_another_thread(lock_path, 0.05) == "timeout"

    assert _acquire_from_another_thread(lock_path, 1.0) == "acquired"


def test_exception_inside_a_nested_block_still_releases(tmp_path):
    """An exception escaping the inner block must not strand the lock."""
    lock_path = tmp_path / "unwind.lock"

    with pytest.raises(RuntimeError, match="boom"):
        with FileLock(lock_path, timeout_seconds=1):
            with FileLock(lock_path, timeout_seconds=1):
                raise RuntimeError("boom")

    assert _acquire_from_another_thread(lock_path, 1.0) == "acquired"


def test_instance_is_clean_after_a_timeout(tmp_path):
    """AC-8: a failed acquisition closes its handle and leaves nothing acquired.

    Otherwise the polling path leaks a descriptor and leaves the instance
    looking acquired — so the same instance must also work on a later, real
    acquisition (external plan review, openai).
    """
    lock_path = tmp_path / "cleanup.lock"
    lock = FileLock(lock_path, timeout_seconds=0.1)

    with _held_by_another_thread(lock_path):
        opened: list = []
        import lib.file_lock as fl  # noqa: PLC0415

        real_open = fl.open if hasattr(fl, "open") else open

        def spy_open(*a, **k):
            fh = real_open(*a, **k)
            opened.append(fh)
            return fh

        fl.open = spy_open           # module-level name lookup inside __enter__
        try:
            with pytest.raises(LockTimeout):
                lock.__enter__()
        finally:
            del fl.open
        # `_fp is None` alone proves nothing — it is None from __init__. What
        # matters is that the handle the failed acquisition OPENED got closed;
        # drop fp.close() from __enter__'s except and this goes red (doubt review).
        assert opened and all(fh.closed for fh in opened), "the failed acquire leaked a handle"
        assert lock._fp is None

    # The BEHAVIOUR, not just the attribute: the failed acquisition must have
    # registered nothing, so the instance really can acquire afterwards and
    # really does exclude another thread while it holds it.
    with lock:
        assert lock._fp is not None
        assert _acquire_from_another_thread(lock_path, 0.05) == "timeout"
    assert lock._fp is None
    assert _acquire_from_another_thread(lock_path, 1.0) == "acquired"
