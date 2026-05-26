"""Process spawn + kill primitives for dev_server services.

Extracted from `shared/scripts/dev_server.py` during B4 split (campaign
`2026-05-25-bloat-cleanup-B-shipwright`). Producer/consumer surface
preserved via package-level re-exports in `__init__.py`.

IMPORTANT (B3 lesson — see B4 spec):
The `resolve_executable` helper lives in `shared/scripts/lib/cmd_resolver.py`.
Importing it at module-top via `from lib.cmd_resolver import ...` cached
the `lib` package from SHARED in `sys.modules` during pytest collection,
which broke plugins that ship their own `lib/` subpackage. To prevent
that recurrence here, the actual import is deferred to `__init__.py`
(which only runs when the package is explicitly imported, never during
unrelated pytest collection). `_start_one` dispatches through the
package-level attribute so tests can `monkeypatch.setattr(
dev_server, "resolve_executable", ...)`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _resolve_via_pkg(name: str) -> str:
    """Call the package-bound `resolve_executable`.

    `__init__.py` binds `resolve_executable` on the package (real or
    test-monkeypatched). We retrieve it via `sys.modules[__package__]`
    so that test monkeypatches against `dev_server.resolve_executable`
    are honored without us holding a stale local reference.
    """
    pkg = sys.modules[__package__]
    fn = getattr(pkg, "resolve_executable", None)
    if fn is None:
        # Package wasn't initialized via __init__.py (extremely unusual).
        # Last-resort: import directly. The B3 sys.modules['lib'] hazard
        # only matters at collection time — by the time _start_one runs
        # we are already in a test that explicitly imported dev_server,
        # so the cache pollution would have already happened upstream
        # if it were going to. This is the safe fallback path.
        scripts_dir = Path(__file__).resolve().parent.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from lib.cmd_resolver import resolve_executable as _real  # noqa: E402
        return _real(name)
    return fn(name)


def _is_pid_running(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in result.stdout
        except (subprocess.TimeoutExpired, OSError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _start_one(service: dict, cwd: Path) -> tuple[Any, dict]:
    """Spawn the service's process. Returns (proc, record)."""
    # Always use POSIX-style shlex parsing — strips quotes from the command
    # string. Windows Popen with a list calls list2cmdline() to re-quote
    # safely, so the cross-platform contract is: profile authors write
    # POSIX-quoted commands; subprocess handles platform-specific argv
    # encoding.
    cmd_parts = shlex.split(service["command"], posix=True)
    if cmd_parts:
        # Resolve npm/npx/etc. to their .cmd shim on Windows. shell stays
        # False — never trust profile-supplied command strings to a shell.
        cmd_parts[0] = _resolve_via_pkg(cmd_parts[0])
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd_parts,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    # _service_url is in profile_config; the relative-import is a
    # package-internal one, NOT the brittle `from lib.X` pattern.
    from .profile_config import _service_url

    record = {
        "name": service["name"],
        "pid": proc.pid,
        "port": service["port"],
        "host": service.get("host", "localhost"),
        "scheme": service.get("scheme", "http"),
        "command": service["command"],
        "ready_path": service.get("ready_path"),
        "ready_timeout_seconds": int(service.get("ready_timeout_seconds", 60)),
        "url": _service_url(service),
        "primary": bool(service.get("primary", False)),
    }
    return proc, record


def _kill_one(record: dict) -> dict:
    """Kill a single service's process tree. Non-fatal on 'not found'."""
    pid = record.get("pid")
    if not pid:
        return {"name": record.get("name"), "pid": None, "killed": False, "reason": "no_pid"}
    if not _is_pid_running(pid):
        return {"name": record.get("name"), "pid": pid, "killed": False, "reason": "not_running"}
    try:
        if os.name == "nt":
            res = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
            killed = res.returncode == 0
            reason = None if killed else f"taskkill_rc={res.returncode}"
            return {"name": record.get("name"), "pid": pid, "killed": killed, "reason": reason}
        else:
            import signal as _signal
            os.kill(pid, _signal.SIGTERM)
            time.sleep(0.5)
            if _is_pid_running(pid):
                os.kill(pid, _signal.SIGKILL)
            return {"name": record.get("name"), "pid": pid, "killed": True}
    except subprocess.TimeoutExpired:
        return {"name": record.get("name"), "pid": pid, "killed": False, "reason": "taskkill_timeout"}
    except OSError as e:
        return {"name": record.get("name"), "pid": pid, "killed": False, "reason": str(e)}


class _StartFailed(Exception):
    def __init__(self, service_name: str, reason: str):
        super().__init__(f"service {service_name!r} failed: {reason}")
        self.service_name = service_name
        self.reason = reason


def _rollback_and_report(
    started: list[tuple[Any, dict]], error: str
) -> dict:
    """Kill every started service in reverse, return error JSON. State already absent.

    Dispatches kill via the package surface so test monkeypatches against
    `dev_server._kill_one` propagate into the rollback path.
    """
    pkg = sys.modules[__package__]
    kill_results: list[dict] = []
    for proc, record in reversed(started):
        try:
            kill_results.append(pkg._kill_one(record))
        except Exception as e:  # pragma: no cover — defensive
            kill_results.append({
                "name": record.get("name"), "pid": record.get("pid"),
                "killed": False, "reason": f"exception: {e}",
            })
    return {
        "running": False,
        "error": error,
        "services": [rec for _, rec in started],
        "rollback": list(reversed(kill_results)),
    }
