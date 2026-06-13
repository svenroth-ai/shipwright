"""Tests for the shared ``FileLock`` class in ``shared/scripts/lib/file_lock.py``.

The class is the block-until-acquired append-log mutex extracted from the
near-identical copies that used to live in ``tools/record_event.py`` and
``triage.py`` (iterate-2026-06-13-shc-file-lock). Both call sites import it as
``FileLock as _FileLock``. These tests pin the two behaviours the extraction
must preserve:

1. mutual exclusion — a held lock blocks a second acquirer until release;
2. parent-dir creation — ``__enter__`` creates a missing lock-file parent
   directory (the triage-variant superset behaviour both sites unify on).

The pre-existing ``test_record_event.py`` and ``test_triage_storage.py`` cover
the call sites; this file covers the primitive directly.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_TOOLS = _SCRIPTS / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from lib.file_lock import FileLock  # noqa: E402


def test_enter_creates_missing_parent_dir(tmp_path):
    """``__enter__`` must mkdir the lock file's parent (superset behaviour).

    Acquiring a lock whose parent directory does not yet exist must not raise
    — this is the strict superset the triage variant carried and that the
    record_event variant lacked. A first-ever append into a not-yet-created
    ``.shipwright/`` directory relies on it.
    """
    lock_path = tmp_path / "nested" / "deeper" / "data.jsonl.lock"
    assert not lock_path.parent.exists()

    with FileLock(lock_path):
        assert lock_path.parent.is_dir()
        assert lock_path.exists()


def test_mutual_exclusion_blocks_second_acquirer(tmp_path):
    """A second acquirer blocks until the first releases the lock.

    Thread A holds the lock for a short window; thread B can only enter after
    A exits. The recorded acquisition order proves serialization (B never
    overlaps A's critical section).
    """
    lock_path = tmp_path / "mutex.lock"
    order: list[str] = []
    a_holding = threading.Event()
    release_a = threading.Event()

    def worker_a():
        with FileLock(lock_path):
            order.append("a-enter")
            a_holding.set()
            # Hold the lock until the test signals release, so B must wait.
            release_a.wait(timeout=5)
            order.append("a-exit")

    def worker_b():
        # Ensure A grabs the lock first.
        a_holding.wait(timeout=5)
        with FileLock(lock_path):
            order.append("b-enter")

    ta = threading.Thread(target=worker_a)
    tb = threading.Thread(target=worker_b)
    ta.start()
    assert a_holding.wait(timeout=5), "worker A never acquired the lock"
    tb.start()

    # Give B a moment to attempt acquisition; it must NOT have entered yet
    # because A still holds the lock.
    time.sleep(0.05)
    assert "b-enter" not in order, "B entered while A held the lock"

    # Release A; B should now proceed.
    release_a.set()
    ta.join(timeout=5)
    tb.join(timeout=5)

    assert order == ["a-enter", "a-exit", "b-enter"], order


def test_lock_is_reusable_after_release(tmp_path):
    """The same lock path can be re-acquired sequentially after release."""
    lock_path = tmp_path / "reuse.lock"
    for _ in range(3):
        with FileLock(lock_path):
            pass  # acquire + release; must not raise on re-entry next loop
    assert lock_path.exists()


def test_both_call_sites_alias_the_same_shared_class():
    """``record_event._FileLock`` and ``triage._FileLock`` are the shared class.

    The extraction preserves the historical private name on BOTH modules
    (external consumers + the F14 monkeypatch reach into them). External review
    (OpenAI #2) asked for a compatibility assertion that the alias resolves to
    the one shared class — so a future edit can't accidentally re-fork a local
    copy on one side without this test going red.
    """
    import record_event  # noqa: PLC0415
    import triage  # noqa: PLC0415

    assert record_event._FileLock is FileLock
    assert triage._FileLock is FileLock
    assert record_event._FileLock is triage._FileLock
