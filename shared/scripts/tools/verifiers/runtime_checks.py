"""Runtime reconciliation checks (zombie-task detection).

Iterate 12.0 shipped this module as a SKIPPED stub. Iterate 12.0b
replaces the stub with a real implementation now that the webui
TypeScript side emits `task_orphaned` events and the startup
reconciliation loop is in place.

The check replays ``shipwright_events.jsonl`` into a task-state dict
(same idempotency rules as ``event-store.ts::processEvent``) and
cross-checks every task still in ``running`` status against the
governor's ``pids.json``. A task whose event-store status is
``running`` but whose PID is not in ``pids.json`` — or whose PID is in
``pids.json`` but not actually alive — is a zombie, and the check
returns a WARNING (not an error: a transient race during a heartbeat
tick can produce the same symptom, and blocking iterate completion on
a transient is worse than a warning the user can investigate).

This is a single-file authoritative check per webui project. The
governor's PID file lives under ``.shipwright-webui/pids.json`` next
to the webui registry, but when the verifier runs against a target
project it operates on whichever PID file the project passes in
(default: ``<project_root>/.shipwright-webui/pids.json`` if present,
otherwise no PID file → no zombie warnings).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import CheckResult, Severity, read_events_jsonl

_WINDOWS = os.name == "nt"


def _replay_task_states(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Minimal event-replay to derive current task status.

    Mirrors ``webui/server/src/core/event-store.ts::processEvent`` for
    the subset of event types that move status: ``task_created`` →
    pending, ``phase_started`` → running, ``work_completed`` → done,
    ``work_failed`` → failed, ``task_cancelled`` → cancelled,
    ``task_orphaned`` → orphaned (with idempotency: only applied if
    still running). Deliberately skips the task_created → title/desc
    parsing path — this function only needs the status dimension.
    """
    states: dict[str, dict[str, Any]] = {}
    for event in events:
        etype = event.get("type")
        task_id = event.get("task_id")
        if not task_id or not isinstance(task_id, str):
            continue

        if etype == "task_created":
            states[task_id] = {
                "id": task_id,
                "status": "pending",
                "project_id": event.get("project_id", ""),
                "updated_at": event.get("timestamp", ""),
            }
        elif etype == "phase_started":
            task = states.get(task_id)
            if task:
                task["status"] = "running"
                task["updated_at"] = event.get("timestamp", task["updated_at"])
        elif etype == "work_completed":
            task = states.get(task_id)
            if task:
                task["status"] = "done"
                task["updated_at"] = event.get("timestamp", task["updated_at"])
        elif etype == "work_failed":
            task = states.get(task_id)
            if task:
                task["status"] = "failed"
                task["updated_at"] = event.get("timestamp", task["updated_at"])
        elif etype == "task_cancelled":
            task = states.get(task_id)
            if task:
                task["status"] = "cancelled"
                task["updated_at"] = event.get("timestamp", task["updated_at"])
        elif etype == "task_orphaned":
            task = states.get(task_id)
            # Idempotency — mirror the event-store guard
            if task and task["status"] == "running":
                task["status"] = "orphaned"
                task["updated_at"] = event.get("timestamp", task["updated_at"])
    return states


def _load_pids(pid_file: Path) -> dict[str, dict[str, Any]]:
    """Parse ``pids.json`` into ``{taskId: {pid, spawnedAt}}``."""
    if not pid_file.exists():
        return {}
    try:
        data = json.loads(pid_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and isinstance(entry.get("taskId"), str):
                out[entry["taskId"]] = entry
    return out


def _pid_is_alive(pid: int) -> bool:
    """Best-effort liveness check cross-platform.

    On POSIX, ``os.kill(pid, 0)`` raises ``ProcessLookupError`` when no
    process with that PID exists. Windows needs a process-handle query:
    ``os.kill(pid, 0)`` sends ``CTRL_C_EVENT`` there and can terminate the
    verifier's own console process group.
    """
    if pid <= 0:
        return False
    if _WINDOWS:
        return _windows_pid_is_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _windows_pid_is_alive(pid: int) -> bool:
    """Query Windows process state without delivering a console signal."""
    if not 0 < pid <= 0xFFFFFFFF:
        return False

    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    error_access_denied = 5
    wait_timeout = 258

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    ctypes.set_last_error(0)
    handle = open_process(
        process_query_limited_information | synchronize,
        False,
        pid,
    )
    if not handle:
        # A protected process can deny query access while still being alive.
        return ctypes.get_last_error() == error_access_denied

    try:
        # A zero-timeout wait reports WAIT_TIMEOUT only while the process is
        # still running. Unlike GetExitCodeProcess, this cannot confuse a
        # terminated process whose legitimate exit code is STILL_ACTIVE (259).
        return wait_for_single_object(handle, 0) == wait_timeout
    finally:
        close_handle(handle)


def check_no_zombie_running_tasks(
    project_root: Path,
    *,
    pid_file: Path | None = None,
) -> CheckResult:
    """Return a WARNING for every task still ``running`` without a live PID.

    The verifier passes if there are no zombies, or if the project has
    no ``pids.json`` to compare against (unmanaged project — nothing to
    verify). The warning-severity is deliberate: a heartbeat tick might
    be in flight right when the check runs, and blocking the iterate
    completion on a transient is worse than a visible warning.
    """
    name = "runtime zombie_tasks"

    events = read_events_jsonl(project_root)
    if not events:
        return CheckResult(name, True, "no events to reconcile")

    pid_path = pid_file or (project_root / ".shipwright-webui" / "pids.json")
    pids = _load_pids(pid_path)

    states = _replay_task_states(events)
    running = [s for s in states.values() if s["status"] == "running"]
    if not running:
        return CheckResult(name, True, "no running tasks")

    zombies: list[str] = []
    for task in running:
        pid_entry = pids.get(task["id"])
        if not pid_entry:
            zombies.append(f"{task['id']} (no PID file entry)")
            continue
        pid = pid_entry.get("pid")
        if not isinstance(pid, int) or not _pid_is_alive(pid):
            zombies.append(f"{task['id']} (pid={pid} not alive)")

    if zombies:
        return CheckResult(
            name,
            False,
            f"{len(zombies)} zombie task(s): {', '.join(zombies[:3])}"
            + (" …" if len(zombies) > 3 else ""),
            severity=Severity.WARNING.value,
        )

    return CheckResult(name, True, f"{len(running)} running task(s), all PIDs alive")


def run_all_checks(project_root: Path) -> list[CheckResult]:
    """Return the runtime check suite.

    Iterate 12.0b replaces the 12.0 stub with a single real check
    (``check_no_zombie_running_tasks``). Future runtime checks
    (e.g. stale lock files, orphaned chat-history sessions) can be
    appended without API changes.
    """
    return [check_no_zombie_running_tasks(project_root)]
