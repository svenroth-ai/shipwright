"""Shared primitives for the phase-task lifecycle modules.

The per-project lock, run_config read/write helpers, result builders, the
lock-timeout guard and the owner+version CAS check. Extracted from
``phase_task_lifecycle`` so the transition modules (lifecycle, recovery,
planning, lookup) can all depend on one leaf without importing each other;
``phase_task_lifecycle`` re-exports every name, so existing imports are unchanged.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, ParamSpec

# Local lib imports — sibling modules (run_config_store) live next to us
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_config_store import (  # noqa: E402
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    LockTimeout,
    atomic_write_json,
    durable_read_text,
    lock_path,
)

# Own insert (mirrors run_config_store.py's), not relied-upon import order —
# an ordering an autofixer may reshuffle (ADR-045).
_SHARED_LIB = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from file_lock import FileLock  # noqa: E402

CONFIG_NAME = "shipwright_run_config.json"

TERMINAL_STATUSES = frozenset({"done", "failed", "skipped"})

# The CAS ``version`` a task without one carries. Every task is created at 1, so an
# old-format record that lacks the key reads as 1 at every reader (``task_version``).
DEFAULT_TASK_VERSION = 1


def task_version(task: dict[str, Any]) -> int:
    """A task's CAS ``version``; absent reads as ``DEFAULT_TASK_VERSION``."""
    return int(task.get("version", DEFAULT_TASK_VERSION))

# Plugin-name -> phase mapping. Used by phase_session_start.py to know its
# own expected phase from CLAUDE_PLUGIN_ROOT. Centralised here so callers
# stay consistent.
PLUGIN_PHASE_MAP: dict[str, str] = {
    "shipwright-project": "project",
    "shipwright-design": "design",
    "shipwright-plan": "plan",
    "shipwright-build": "build",
    "shipwright-test": "test",
    "shipwright-security": "security",
    "shipwright-changelog": "changelog",
    "shipwright-deploy": "deploy",
}


# ---------------------------------------------------------------------------
# Cross-platform file lock
# ---------------------------------------------------------------------------

class _PhaseTasksLock(FileLock):
    """Per-project lock for atomic phase_tasks[] mutations.

    Delegates to ``lib.file_lock.FileLock`` instead of a third literal copy
    of the wait/lock loop — the old copy blocked unboundedly on POSIX, spun
    forever on Windows, and would self-deadlock on same-thread nesting with
    no diagnostic, the same defects ``trg-dc013d82`` #24 fixed in the other
    two copies (``trg-2e961fee``). Targets
    ``run_config_store.lock_path()`` directly (not a locally re-declared
    path string) — the same file ``run_config_store.run_config_lock`` /
    ``append_phase_history``'s ``file_lock`` target, so all three exclude
    each other at the OS level regardless of which acquired it, structurally
    rather than by two literals staying in sync by convention (measured
    both directions — see ``test_phase_tasks_lock.py``). Uses
    ``run_config_store.DEFAULT_LOCK_TIMEOUT_SECONDS`` (30s), not the class's
    600s default sized for the triage sweep — this guards the same fast RMW
    the 30s bound was chosen for. Every caller (lifecycle/recovery/planning modules) catches
    :class:`LockTimeout` to keep the module's ``ok: False`` contract.

    Reentrancy is a hang guardrail, not licence to nest: no caller does
    today (verified by grep), and every critical section here is RMW, so a
    future nested call would silently clobber the outer write instead of
    deadlocking loudly. The live trap: ``complete_phase_task`` calls
    ``mark_phase_failed`` on its ``result.ok is False`` branch, and that
    call must stay OUTSIDE ``complete_phase_task``'s own ``with`` block —
    moving it inside would now silently succeed (reentrant) instead of
    deadlocking, and clobber the outer function's in-memory config.

    Reentrancy is scoped to :class:`FileLock` acquirers on this path, NOT
    to the sidecar file itself (doubt-reviewer, D2): ``run_config_lock``
    and ``append_phase_history``'s ``file_lock`` use the ``file_lock``
    CONTEXT-MANAGER FUNCTION, which never registers with the same-thread
    registry :class:`FileLock` checks. Nesting either of those inside a
    held ``_PhaseTasksLock`` (or vice versa) on the same thread still waits
    out the full bound and then fails — silently, as an ``ok: False`` here,
    rather than the loud deadlock it used to be. No such nesting exists
    today (verified by grep); this note exists so a future one is written
    knowing the exclusion, not assuming it.
    """

    def __init__(self, project_root: Path):
        super().__init__(lock_path(project_root),
                         timeout_seconds=DEFAULT_LOCK_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# Internal read/write helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_config(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIG_NAME
    if not path.exists():
        raise FileNotFoundError(f"{CONFIG_NAME} not found at {project_root}")
    return json.loads(durable_read_text(path))  # delete-pending safe (WP2/F12)


def _write_config(project_root: Path, config: dict[str, Any]) -> None:
    config["updated_at"] = _now_iso()
    atomic_write_json(project_root / CONFIG_NAME, config)  # atomic; readers never see a partial write (WP2/F12)


def _find_task(config: dict[str, Any], phase_task_id: str) -> Optional[dict[str, Any]]:
    for t in config.get("phase_tasks", []):
        if t.get("phaseTaskId") == phase_task_id:
            return t
    return None


def _ok(phase_task: dict[str, Any], **extras: Any) -> dict[str, Any]:
    out = {"ok": True, "phase_task": phase_task}
    out.update(extras)
    return out


def _fail(reason: str, *, message: str, **extras: Any) -> dict[str, Any]:
    out = {"ok": False, "reason": reason, "blockMessage": message}
    out.update(extras)
    return out


def _new_phase_task_id() -> str:
    return "ptk-" + uuid.uuid4().hex[:8]


_P = ParamSpec("_P")


def _guard_lock_timeout(fn: Callable[_P, dict[str, Any]]) -> Callable[_P, dict[str, Any]]:
    """Convert a bounded ``_PhaseTasksLock`` timeout into ``ok: False``.

    Without this, ``LockTimeout`` — the ONE new exception
    ``_PhaseTasksLock`` introduced by no longer blocking forever (internal
    plan review, trg-2e961fee) — would escape past the module docstring's
    Public API contract (every function returns a result dict). It does
    NOT make that contract absolute: a missing config still raises
    ``FileNotFoundError`` (``_read_config``), and the lock sidecar's
    truncating ``open(..., "w")`` (``file_lock.py``, ahead of acquisition)
    can still raise a raw ``OSError`` — both pre-existing, both unchanged by
    this fix. Wraps the whole function rather than just its ``with`` block
    on purpose: the only lock any of the six decorated functions takes
    today is this one — a future function that also needs an unrelated
    lock must not reuse this decorator over that block, or a timeout on the
    OTHER lock would be mis-reported as ``lock_timeout`` on this one.

    ``retryable=True`` (doubt-reviewer, D1): every OTHER ``ok: False``
    reason this module produces is a determination about state — retrying
    ``stale_version`` or `wrong_skill`` cannot help. A lock timeout is the
    opposite: contention is expected to clear. Without a machine-readable
    marker a caller (or a human reading ``freeze_splits_failed`` after
    ``single_session_apply.py`` renames the reason) cannot tell the two
    classes apart from the dict alone.
    """
    @wraps(fn)
    def _wrapped(*args: _P.args, **kwargs: _P.kwargs) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except LockTimeout as exc:
            return _fail("lock_timeout", message=f"phase-tasks lock: {exc}", retryable=True)
    return _wrapped


# ---------------------------------------------------------------------------
# CAS check (owner + version)
# ---------------------------------------------------------------------------

def _check_owner_version(
    task: dict[str, Any], session_uuid: str, expected_version: int,
) -> Optional[dict[str, Any]]:
    """Validate caller owns the claim and the version is current.

    Returns None if OK. Returns a fail dict otherwise.
    Used by complete_phase_task and mark_phase_failed.
    """
    actual_version = task_version(task)
    if actual_version != int(expected_version):
        return _fail(
            "stale_version",
            message=(
                f"Stale-session error: caller has version {expected_version} but "
                f"task {task['phaseTaskId']} is now at version {actual_version} "
                f"(another session has taken ownership via recover-phase-task)."
            ),
            actual_version=actual_version,
            expected_version=int(expected_version),
        )

    claimed_by = task.get("claimedBySessionUuid")
    if claimed_by != session_uuid:
        return _fail(
            "stale_session",
            message=(
                f"Stale-session error: task {task['phaseTaskId']} is claimed by "
                f"{claimed_by!r}, not {session_uuid!r}."
            ),
            claimed_by=claimed_by,
        )

    if task.get("status") != "in_progress":
        # Don't reject if already terminal-by-this-owner — caller checks idempotency
        # at the public function level. This guard catches truly bad state.
        if task.get("status") not in TERMINAL_STATUSES:
            return _fail(
                "invalid_status_for_completion",
                message=f"Cannot complete/fail from status {task.get('status')!r}.",
            )
    return None
