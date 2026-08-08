"""``_PhaseTasksLock`` now delegates to the shared ``file_lock.FileLock`` (trg-2e961fee).

Was a third literal copy of the wait/lock mechanics -- unbounded on POSIX
(``fcntl.flock(LOCK_EX)`` blocks forever), a flat 1 ms Windows spin with no
deadline, and no reentrancy, so a same-thread nested acquisition would have
self-deadlocked with no diagnostic. The exact two defects ``trg-dc013d82``
finding 24 fixed in the other two copies (``file_lock.FileLock`` and the
context-manager ``file_lock`` function). This pins the DELEGATION, not the
underlying bounded/reentrant mechanics -- those are already covered
exhaustively in ``shared/tests/test_file_lock_bounded.py``; re-testing them
here would just be the fourth copy this fix exists to remove.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
_SHARED_LIB = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib"
sys.path.insert(0, str(_SHARED_LIB))

from file_lock import FileLock, file_lock  # noqa: E402
from phase_task_lifecycle import (  # noqa: E402
    LockTimeout,
    _PhaseTasksLock,
    claim_phase_task,
    complete_phase_task,
    freeze_splits,
    mark_phase_failed,
    plan_next_phase,
    recover_phase_task,
)
from run_config_store import DEFAULT_LOCK_TIMEOUT_SECONDS, lock_path  # noqa: E402

# Every function `@_guard_lock_timeout` wraps, paired with placeholder kwargs.
# The timeout fires during lock ACQUISITION -- before any body logic reads
# phase_tasks[] -- so the argument values themselves are never inspected;
# only their presence/shape needs to satisfy each signature.
_GUARDED_CALLS = [
    pytest.param(
        claim_phase_task,
        {"phase_task_id": "ptk-x", "session_uuid": "s", "expected_phase": "build"},
        id="claim_phase_task",
    ),
    pytest.param(
        mark_phase_failed,
        {"phase_task_id": "ptk-x", "session_uuid": "s", "expected_version": 1, "error": "e"},
        id="mark_phase_failed",
    ),
    pytest.param(
        complete_phase_task,
        {"phase_task_id": "ptk-x", "session_uuid": "s", "expected_version": 1, "result": {"ok": True}},
        id="complete_phase_task",
    ),
    pytest.param(
        recover_phase_task,
        {"phase_task_id": "ptk-x"},
        id="recover_phase_task",
    ),
    pytest.param(freeze_splits, {}, id="freeze_splits"),
    pytest.param(
        plan_next_phase,
        {"completed_phase_task_id": "ptk-x"},
        id="plan_next_phase",
    ),
]


def _fast_lock(project_root: Path, timeout_seconds: float = 0.05) -> _PhaseTasksLock:
    """A `_PhaseTasksLock` on `project_root` with its timeout overridden.

    A same-instance attribute override (not a monkeypatched constructor) --
    valid whenever the TEST constructs the lock directly. The parametrized
    guard test below cannot use this: `fn(project_root, **kwargs)`
    constructs its own `_PhaseTasksLock` internally, so only a patched
    `__init__` reaches it.
    """
    lock = _PhaseTasksLock(project_root)
    lock._timeout_seconds = timeout_seconds
    return lock


def test_delegates_to_the_shared_lock_class():
    """Drift guard: a future edit re-inlining lock mechanics here must fail loudly."""
    assert issubclass(_PhaseTasksLock, FileLock)


def test_targets_the_canonical_run_config_lock_path(tmp_path):
    """Same lock file as run_config_store.run_config_lock and append_phase_history's
    file_lock -- all three must exclude each other at the OS level regardless of
    which implementation acquired it (run_config_store's module docstring).

    Asserts against `run_config_store.lock_path()` itself, not a locally
    re-derived path string -- code-reviewer (MEDIUM): re-deriving the
    expression from `_PhaseTasksLock`'s own former local constant would stay
    green even if that constant silently drifted from `run_config_store`'s,
    the exact drift this identity is supposed to rule out.
    """
    lock = _PhaseTasksLock(tmp_path)
    assert lock._lock_path == lock_path(tmp_path)


def test_is_bounded_using_the_run_config_lock_sibling_value(tmp_path):
    """The copy this replaced had no timeout at all in either platform branch.

    Pinned to `run_config_store.DEFAULT_LOCK_TIMEOUT_SECONDS` (30s), NOT
    FileLock's own 600s default -- that default is sized for the triage
    sweep's ~225s worst case, not this lock's fast read-modify-write
    (internal plan review). Inheriting 600s silently would have meant a
    stuck holder on THIS lock produces a ten-minute wait before the
    diagnostic this fix exists to produce, while its two siblings on the
    identical lock file give up in 5s / 30s.
    """
    lock = _PhaseTasksLock(tmp_path)
    assert lock._timeout_seconds == DEFAULT_LOCK_TIMEOUT_SECONDS
    assert lock._timeout_seconds == 30.0


def test_nested_same_thread_acquisition_does_not_self_deadlock(tmp_path):
    """The copy this replaced had no reentrancy: a nested `with` on the same
    thread waited on a lock only the waiting thread could release. Must return
    promptly instead of hanging the test -- a short timeout means a
    regression fails in milliseconds rather than wedging the suite for the
    real 30s bound (code-reviewer, LOW)."""
    outer_ran = inner_ran = False
    with _fast_lock(tmp_path):
        outer_ran = True
        with _fast_lock(tmp_path):
            inner_ran = True
        # Inner released; outer must still hold — proven via the shared
        # class's own exclusion tests, not re-asserted here.
    assert outer_ran and inner_ran


@pytest.mark.parametrize("fn, kwargs", _GUARDED_CALLS)
def test_every_guarded_function_converts_a_lock_timeout_to_ok_false(tmp_path, monkeypatch, fn, kwargs):
    """External plan review (openai, MEDIUM): a single freeze_splits case does not
    prove the other five decorated functions carry the same contract -- one missed
    or malformed `@_guard_lock_timeout` application would leave that operation's
    LockTimeout to escape uncaught into a caller (e.g. single_session_apply.py)
    documented to receive a dict."""
    project_root = tmp_path
    monkeypatch.setattr(_PhaseTasksLock, "__init__",
                        lambda self, root: FileLock.__init__(
                            self, lock_path(root), timeout_seconds=0.05))

    held = threading.Event()
    release = threading.Event()

    def hold():
        with FileLock(lock_path(project_root), timeout_seconds=10):
            held.set()
            release.wait(timeout=10)

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert held.wait(timeout=10)
        result = fn(project_root, **kwargs)
    finally:
        release.set()
        worker.join(timeout=10)

    assert result["ok"] is False
    assert result["reason"] == "lock_timeout"


def test_a_holder_via_the_sibling_a_plus_lock_is_waited_out_not_crashed_into(tmp_path):
    """The untested (risky) cross-implementation direction: run_config_lock's
    non-truncating 'a+' open holds the OS lock first, THEN this class's
    truncating 'w' open runs. Measured on Windows, not just reasoned about
    (internal plan review) -- the truncating open must still bound-wait and
    raise LockTimeout, not crash out of `open()` itself with a raw OSError."""
    sidecar = lock_path(tmp_path)
    held = threading.Event()
    release = threading.Event()

    def hold_via_run_config_lock():
        with file_lock(sidecar, timeout_seconds=10):
            held.set()
            release.wait(timeout=10)

    worker = threading.Thread(target=hold_via_run_config_lock)
    worker.start()
    try:
        assert held.wait(timeout=10)
        with pytest.raises(LockTimeout):
            with _fast_lock(tmp_path, timeout_seconds=1.0):
                pass  # pragma: no cover — acquisition must not succeed
    finally:
        release.set()
        worker.join(timeout=10)
    assert sidecar.exists(), "the sidecar must survive, even truncated"
