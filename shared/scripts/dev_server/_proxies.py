"""Internal proxy stubs — dispatch through the package's attribute table.

Tests rely on monkeypatching the package surface (e.g. `@patch(
"dev_server._is_port_in_use_for_host", ...)` and
`monkeypatch.setattr("dev_server.subprocess.Popen", ...)`). A direct
`from .health import _is_port_in_use_for_host` in `multiservice` would
hold a stale reference to the original health-module function and miss
the patch.

These wrappers solve that by always looking up the name on the package
object (`sys.modules[__package__]`) at call time. `__init__.py` binds
every public name to the corresponding submodule export by default;
tests that patch the package re-bind it temporarily.

This module is internal to the `dev_server` package and is NOT part of
the public surface; it lives outside `__init__.py`'s re-export list so
external callers cannot depend on it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _pkg():
    """Return the live dev_server package module."""
    return sys.modules[__package__]


def _is_port_in_use_for_host(host: str, port: int) -> bool:
    return _pkg()._is_port_in_use_for_host(host, port)


def _probe_hosts_for(host: str) -> list[str]:
    return _pkg()._probe_hosts_for(host)


def _wait_for_service(svc: dict, proc, deadline: float) -> tuple[bool, str]:
    return _pkg()._wait_for_service(svc, proc, deadline)


def _is_pid_running(pid: int) -> bool:
    return _pkg()._is_pid_running(pid)


def _kill_one(record: dict) -> dict:
    return _pkg()._kill_one(record)


def _start_one(service: dict, cwd: Path):
    return _pkg()._start_one(service, cwd)


def _rollback_and_report(started, error: str) -> dict:
    return _pkg()._rollback_and_report(started, error=error)


def _load_state(cwd: Path):
    return _pkg()._load_state(cwd)


def _save_state_atomic(cwd: Path, state: dict) -> None:
    return _pkg()._save_state_atomic(cwd, state)


def _clear_state(cwd: Path) -> None:
    return _pkg()._clear_state(cwd)
