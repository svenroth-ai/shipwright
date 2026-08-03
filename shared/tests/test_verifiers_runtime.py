"""Tests for shared/scripts/tools/verifiers/runtime_checks.py.

Exercises the iterate 12.0b real implementation: replay events.jsonl to
task-state, cross-check against pids.json, warn on any `running` task
whose PID isn't live.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from tools.verifiers import runtime_checks
from tools.verifiers.common import Severity
from tools.verifiers.runtime_checks import (
    _pid_is_alive,
    _replay_task_states,
    _windows_pid_is_alive,
    check_no_zombie_running_tasks,
    run_all_checks,
)


def write_events(root: Path, events: list[dict]) -> None:
    (root / "shipwright_events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events),
        encoding="utf-8",
    )


def write_pids(root: Path, entries: list[dict]) -> Path:
    pid_dir = root / ".shipwright-webui"
    pid_dir.mkdir(parents=True, exist_ok=True)
    path = pid_dir / "pids.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _replay_task_states
# ---------------------------------------------------------------------------

def test_replay_task_states_mirrors_event_store():
    events = [
        {"type": "task_created", "task_id": "t1", "timestamp": "t0"},
        {"type": "phase_started", "task_id": "t1", "phase": "build", "timestamp": "t1"},
    ]
    states = _replay_task_states(events)
    assert states["t1"]["status"] == "running"


def test_replay_task_states_task_orphaned_idempotent():
    events = [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
        {"type": "task_orphaned", "task_id": "t1"},
        # Second orphan — idempotency guard (already orphaned)
        {"type": "task_orphaned", "task_id": "t1"},
    ]
    states = _replay_task_states(events)
    assert states["t1"]["status"] == "orphaned"


def test_replay_task_states_work_completed_protects_from_late_orphan():
    events = [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
        {"type": "work_completed", "task_id": "t1"},
        # Stale orphan event from a late heartbeat — must not clobber done
        {"type": "task_orphaned", "task_id": "t1"},
    ]
    states = _replay_task_states(events)
    assert states["t1"]["status"] == "done"


def test_replay_task_states_handles_unknown_task_ids():
    events = [
        {"type": "work_completed", "task_id": "ghost"},
    ]
    states = _replay_task_states(events)
    assert "ghost" not in states


# ---------------------------------------------------------------------------
# check_no_zombie_running_tasks
# ---------------------------------------------------------------------------

def test_check_passes_when_no_events(tmp_path):
    result = check_no_zombie_running_tasks(tmp_path)
    assert result.ok is True
    assert "no events" in result.detail.lower()


def test_check_passes_when_no_running_tasks(tmp_path):
    write_events(tmp_path, [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
        {"type": "work_completed", "task_id": "t1"},
    ])
    result = check_no_zombie_running_tasks(tmp_path)
    assert result.ok is True


def test_check_passes_when_running_task_has_live_pid(tmp_path):
    write_events(tmp_path, [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
    ])
    write_pids(tmp_path, [{"taskId": "t1", "pid": 12345}])
    with patch("tools.verifiers.runtime_checks._pid_is_alive", return_value=True):
        result = check_no_zombie_running_tasks(tmp_path)
    assert result.ok is True
    assert "all PIDs alive" in result.detail


def test_check_warns_when_running_task_has_dead_pid(tmp_path):
    write_events(tmp_path, [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
    ])
    write_pids(tmp_path, [{"taskId": "t1", "pid": 99999}])
    with patch("tools.verifiers.runtime_checks._pid_is_alive", return_value=False):
        result = check_no_zombie_running_tasks(tmp_path)
    assert result.ok is False
    assert result.severity == Severity.WARNING.value
    assert "t1" in result.detail


def test_check_warns_when_running_task_has_no_pid_entry(tmp_path):
    write_events(tmp_path, [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
    ])
    write_pids(tmp_path, [])  # empty pids file
    result = check_no_zombie_running_tasks(tmp_path)
    assert result.ok is False
    assert result.severity == Severity.WARNING.value
    assert "no PID file entry" in result.detail


def test_check_pid_file_missing_still_warns_for_running_tasks(tmp_path):
    write_events(tmp_path, [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
    ])
    # No pids.json at all — every running task becomes a zombie because
    # there's no entry to match.
    result = check_no_zombie_running_tasks(tmp_path)
    assert result.ok is False
    assert result.severity == Severity.WARNING.value


def test_check_orphaned_tasks_are_not_zombies(tmp_path):
    """A task that already got its task_orphaned event is not a zombie."""
    write_events(tmp_path, [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
        {"type": "task_orphaned", "task_id": "t1"},
    ])
    write_pids(tmp_path, [])
    result = check_no_zombie_running_tasks(tmp_path)
    assert result.ok is True


def test_check_custom_pid_file_path(tmp_path):
    write_events(tmp_path, [
        {"type": "task_created", "task_id": "t1"},
        {"type": "phase_started", "task_id": "t1", "phase": "build"},
    ])
    custom_path = tmp_path / "alt_pids.json"
    custom_path.write_text(json.dumps([{"taskId": "t1", "pid": 12345}]))
    with patch("tools.verifiers.runtime_checks._pid_is_alive", return_value=True):
        result = check_no_zombie_running_tasks(tmp_path, pid_file=custom_path)
    assert result.ok is True


# ---------------------------------------------------------------------------
# run_all_checks orchestrator
# ---------------------------------------------------------------------------

def test_run_all_checks_returns_single_check(tmp_path):
    results = run_all_checks(tmp_path)
    assert len(results) == 1
    assert "zombie" in results[0].name


# ---------------------------------------------------------------------------
# _pid_is_alive — smoke tests (avoid OS-dependent assertions)
# ---------------------------------------------------------------------------

def test_pid_is_alive_zero_and_negative_false():
    assert _pid_is_alive(0) is False
    assert _pid_is_alive(-1) is False


def test_pid_is_alive_current_process_true():
    # Our own PID is always alive while the test runs.
    assert _pid_is_alive(os.getpid()) is True


def test_pid_is_alive_windows_does_not_send_console_signal():
    with (
        patch.object(runtime_checks, "_WINDOWS", True),
        patch.object(runtime_checks, "_windows_pid_is_alive", return_value=True) as probe,
        patch.object(runtime_checks.os, "kill") as kill,
    ):
        assert _pid_is_alive(os.getpid()) is True
    probe.assert_called_once_with(os.getpid())
    kill.assert_not_called()


def _probe_with_fake_kernel32(kernel32, *, last_error=0, pid=12345):
    with (
        patch.object(ctypes, "WinDLL", return_value=kernel32, create=True),
        patch.object(ctypes, "set_last_error", create=True),
        patch.object(
            ctypes,
            "get_last_error",
            return_value=last_error,
            create=True,
        ),
    ):
        return _windows_pid_is_alive(pid)


@pytest.mark.parametrize(
    ("wait_result", "expected"),
    [
        (258, True),  # WAIT_TIMEOUT: process is still running
        (0, False),  # WAIT_OBJECT_0: process has terminated
        (0xFFFFFFFF, False),  # WAIT_FAILED: liveness is not proven
    ],
)
def test_windows_pid_probe_uses_wait_state_and_closes_handle(wait_result, expected):
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = 321
    kernel32.WaitForSingleObject.return_value = wait_result

    assert _probe_with_fake_kernel32(kernel32) is expected

    kernel32.WaitForSingleObject.assert_called_once_with(321, 0)
    kernel32.GetExitCodeProcess.assert_not_called()
    kernel32.CloseHandle.assert_called_once_with(321)


@pytest.mark.parametrize(
    ("last_error", "expected"),
    [
        (5, True),  # ERROR_ACCESS_DENIED proves the process exists
        (87, False),  # ERROR_INVALID_PARAMETER: no such process
    ],
)
def test_windows_pid_probe_handles_open_process_failures(last_error, expected):
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = 0

    assert _probe_with_fake_kernel32(kernel32, last_error=last_error) is expected

    kernel32.WaitForSingleObject.assert_not_called()
    kernel32.CloseHandle.assert_not_called()


def test_windows_pid_probe_rejects_values_that_do_not_fit_a_dword():
    kernel32 = MagicMock()

    assert _probe_with_fake_kernel32(kernel32, pid=(1 << 32) + os.getpid()) is False
    with patch.object(runtime_checks, "_WINDOWS", True):
        assert _pid_is_alive((1 << 32) + os.getpid()) is False

    kernel32.OpenProcess.assert_not_called()
