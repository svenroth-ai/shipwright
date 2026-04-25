#!/usr/bin/env python3
"""Start/Stop/Status management for the target project's dev server(s).

Supports both single-service profiles (legacy `dev_server: {...}` block) and
multi-service profiles (new `services: [...]` array). Single-service is
internally represented as a one-element list named `"primary"`.

Usage:
    uv run dev_server.py start --profile vite-hono --cwd /path/to/project
    uv run dev_server.py start --cwd /path --services-json '[{...}, {...}]'
    uv run dev_server.py stop --cwd /path/to/project
    uv run dev_server.py status --cwd /path/to/project

Output (JSON, single-service):
    {"running": true, "pid": 12345, "url": "http://localhost:3000",
     "ready": true, "services": [...]}

Output (JSON, multi-service):
    {"running": true, "pid": 101, "url": "http://localhost:5173",
     "ready": true, "services": [{name, pid, port, ...}]}

Top-level `pid`/`url` always reflect the **primary** service.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_FILE = "shipwright_dev_server.json"
STATE_VERSION = 2
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Default service used if no profile / no build_config / no inline JSON.
_DEFAULT_SERVICE = {
    "name": "primary",
    "command": "npm run dev",
    "host": "localhost",
    "scheme": "http",
    "port": 3000,
    "ready_path": "/",
    "ready_timeout_seconds": 60,
    "primary": True,
}

# Profile-specific dev_server overrides (legacy single-service map).
PROFILE_DEV_SERVERS: dict[str, dict] = {
    "supabase-nextjs": {
        "command": "npm run dev",
        "port": 3000,
        "ready_timeout_seconds": 60,
        "ready_path": "/",
    },
}


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def _profiles_dir() -> Path:
    """Resolve the shared/profiles directory relative to this script."""
    return Path(__file__).resolve().parent.parent / "profiles"


def _load_profile_data(profile_name: str | None) -> dict | None:
    """Load <profiles_dir>/<name>.json. Falls back to PROFILE_DEV_SERVERS map."""
    if not profile_name:
        return None
    profiles_dir = _profiles_dir()
    candidate = profiles_dir / f"{profile_name}.json"
    if candidate.exists():
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    # Fallback: legacy in-script map for very old callers
    if profile_name in PROFILE_DEV_SERVERS:
        return {"dev_server": PROFILE_DEV_SERVERS[profile_name]}
    return None


def _normalize_legacy_dev_server(block: dict) -> dict:
    """Wrap a legacy `dev_server` block as a single-service entry."""
    return {
        "name": "primary",
        "command": block.get("command", _DEFAULT_SERVICE["command"]),
        "host": block.get("host", "localhost"),
        "scheme": block.get("scheme", "http"),
        "port": int(block.get("port", _DEFAULT_SERVICE["port"])),
        "ready_path": block.get("ready_path", _DEFAULT_SERVICE["ready_path"]),
        "ready_timeout_seconds": int(
            block.get("ready_timeout_seconds", _DEFAULT_SERVICE["ready_timeout_seconds"])
        ),
        "primary": True,
    }


def _normalize_service_entry(entry: dict, default_primary: bool = False) -> dict:
    """Apply defaults to a `services[]` entry.

    Type coercion is intentionally minimal — `_validate_services` raises
    clear per-field errors before any dangerous coercion runs.
    """
    return {
        "name": entry.get("name"),
        "command": entry.get("command"),
        "host": entry.get("host", "localhost"),
        "scheme": entry.get("scheme", "http"),
        "port": entry.get("port"),
        "ready_path": entry.get("ready_path"),
        "ready_timeout_seconds": entry.get("ready_timeout_seconds", 60),
        "depends_on": entry.get("depends_on") or [],
        "primary": bool(entry.get("primary", default_primary)),
    }


def _service_url(service: dict) -> str:
    host = service.get("host", "localhost")
    scheme = service.get("scheme", "http")
    port = service["port"]
    # IPv6 needs bracketing in URLs
    host_part = f"[{host}]" if ":" in str(host) else host
    return f"{scheme}://{host_part}:{port}"


def _get_services(
    profile_name: str | None, cwd: Path
) -> tuple[list[dict], list[str]]:
    """Resolve a normalized service list + warning messages.

    Resolution chain:
      1. profile JSON has `services: [...]` → use it (warn if `dev_server`
         block also present).
      2. profile JSON has only `dev_server: {...}` → wrap as single-service.
      3. shipwright_build_config.json has `dev_url` → derive single service
         from URL.
      4. fallback to _DEFAULT_SERVICE.

    Returns (services, warnings). Warnings are NOT printed here — top-level
    `cmd_*` functions emit them once via stderr.
    """
    warnings: list[str] = []
    profile_data = _load_profile_data(profile_name)
    return _services_from_profile_data(profile_data, cwd, warnings)


def _services_from_profile_data(
    profile_data: dict | None, cwd: Path, warnings: list[str]
) -> tuple[list[dict], list[str]]:
    if profile_data and "services" in profile_data:
        if "dev_server" in profile_data:
            warnings.append(
                "both 'services' and 'dev_server' present in profile; ignoring 'dev_server'"
            )
        raw = profile_data["services"]
        if not isinstance(raw, list) or len(raw) == 0:
            raise ValueError("profile 'services' must be a non-empty array")
        services: list[dict] = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise ValueError(f"services[{i}] must be an object")
            services.append(_normalize_service_entry(entry))
        return services, warnings

    if profile_data and "dev_server" in profile_data:
        return [_normalize_legacy_dev_server(profile_data["dev_server"])], warnings

    # Build config fallback
    build_config = cwd / "shipwright_build_config.json"
    if build_config.exists():
        try:
            data = json.loads(build_config.read_text(encoding="utf-8"))
            dev_url = data.get("dev_url")
            if dev_url:
                parsed = urlparse(dev_url)
                host = parsed.hostname or "localhost"
                scheme = parsed.scheme or "http"
                port = parsed.port or 3000
                return ([{
                    **_DEFAULT_SERVICE,
                    "host": host,
                    "scheme": scheme,
                    "port": port,
                }], warnings)
        except (json.JSONDecodeError, OSError):
            pass

    return [dict(_DEFAULT_SERVICE)], warnings


# Test-friendly accessor: lets tests pass profile_data inline instead of a name.
def _get_services_for_test(
    profile_data: dict | None, cwd: Path
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    services, warnings = _services_from_profile_data(profile_data, cwd, warnings)
    _validate_services(services)
    return services, warnings


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def _validate_services(services: list[dict]) -> None:
    """Validate normalized service list. Raises ValueError on any defect."""
    if not isinstance(services, list) or len(services) == 0:
        raise ValueError("services must be a non-empty list")

    names_seen: set[str] = set()
    primaries = 0
    for i, s in enumerate(services):
        name = s.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"services[{i}].name is empty or not a string")
        if name in names_seen:
            raise ValueError(f"duplicate service name: {name}")
        names_seen.add(name)
        cmd = s.get("command")
        if not cmd or not isinstance(cmd, str):
            raise ValueError(f"services[{i}].command is missing or not a string")
        port = s.get("port")
        if not isinstance(port, int) or isinstance(port, bool):
            raise ValueError(
                f"services[{i}].port must be an integer (got {type(port).__name__})"
            )
        rts = s.get("ready_timeout_seconds", 60)
        if not isinstance(rts, int) or isinstance(rts, bool):
            raise ValueError(
                f"services[{i}].ready_timeout_seconds must be an integer "
                f"(got {type(rts).__name__} {rts!r})"
            )
        deps = s.get("depends_on") or []
        if not isinstance(deps, list):
            raise ValueError(
                f"services[{i}].depends_on must be a list of strings"
            )
        for j, d in enumerate(deps):
            if not isinstance(d, str):
                raise ValueError(
                    f"services[{i}].depends_on[{j}] must be a string "
                    f"(got {type(d).__name__} {d!r})"
                )
        host = s.get("host", "localhost")
        if host not in LOOPBACK_HOSTS:
            raise ValueError(
                f"services[{i}].host must be a loopback address "
                f"(localhost / 127.0.0.1 / ::1); got {host!r}"
            )
        if s.get("primary"):
            primaries += 1

    if primaries > 1:
        raise ValueError("multiple services declare primary: true; at most one allowed")

    # Default primary if no explicit one
    if primaries == 0:
        services[0]["primary"] = True

    # depends_on validation
    for s in services:
        deps = s.get("depends_on") or []
        for d in deps:
            if d == s["name"]:
                raise ValueError(f"service {s['name']!r} has self dependency")
            if d not in names_seen:
                raise ValueError(
                    f"service {s['name']!r} depends_on missing target {d!r}"
                )

    # Cycle check via topo sort attempt
    try:
        _topo_sort(services)
    except ValueError as e:
        if "cycle" in str(e).lower():
            raise
        raise


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

def _topo_sort(services: list[dict]) -> list[list[dict]]:
    """Return services grouped into layers; each layer can start in parallel.

    Within a layer, declaration order is preserved as the deterministic
    tiebreaker. Cycles raise ValueError.
    """
    by_name = {s["name"]: s for s in services}
    remaining = {s["name"]: set(s.get("depends_on") or []) for s in services}
    declaration_order = [s["name"] for s in services]

    layers: list[list[dict]] = []
    placed: set[str] = set()

    while remaining:
        # Names whose deps are all placed
        ready = [
            n for n in declaration_order
            if n in remaining and remaining[n].issubset(placed)
        ]
        if not ready:
            raise ValueError(
                f"dependency cycle detected among services: {sorted(remaining.keys())}"
            )
        layers.append([by_name[n] for n in ready])
        for n in ready:
            placed.add(n)
            del remaining[n]

    return layers


def _pick_primary(services: list[dict]) -> dict:
    for s in services:
        if s.get("primary"):
            return s
    return services[0]


# ---------------------------------------------------------------------------
# Probes (port + HTTP)
# ---------------------------------------------------------------------------

def _is_port_in_use_for_host(host: str, port: int) -> bool:
    """Probe whether a TCP listener is accepting connections at host:port."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def _is_port_in_use(port: int) -> bool:  # legacy compat for tests/import sites
    return _is_port_in_use_for_host("127.0.0.1", port) or _is_port_in_use_for_host("::1", port)


def _probe_hosts_for(service_host: str) -> list[str]:
    """Return the list of host literals to probe for a service's host."""
    if service_host == "localhost":
        return ["127.0.0.1", "::1"]
    return [service_host]


def _http_probe(url: str, timeout: float = 2.0) -> bool:
    """Issue a GET; accept 2xx/3xx as ready. Errors / 4xx / 5xx → not ready."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            return 200 <= status < 400
    except urllib.error.HTTPError as e:
        return 200 <= e.code < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _wait_for_service(service: dict, proc, deadline: float) -> tuple[bool, str]:
    """Poll until ready or deadline. See plan §AC3."""
    host = service.get("host", "localhost")
    port = service["port"]
    ready_path = service.get("ready_path")
    scheme = service.get("scheme", "http")
    probe_hosts = _probe_hosts_for(host)

    while True:
        # 1. Liveness
        if proc is not None and proc.poll() is not None:
            return False, "process_exited"

        # 2. Port probe
        port_open_host = None
        for ph in probe_hosts:
            if _is_port_in_use_for_host(ph, port):
                port_open_host = ph
                break

        if port_open_host is None:
            if time.time() >= deadline:
                return False, "timeout"
            time.sleep(0.5)
            continue

        # 3. No ready_path → port-open is enough
        if not ready_path:
            return True, ""

        # 4. HTTP probe
        url_host = host if host == "localhost" else port_open_host
        # IPv6 literal needs bracketing
        url_host_part = f"[{url_host}]" if ":" in url_host else url_host
        url = f"{scheme}://{url_host_part}:{port}{ready_path}"
        if _http_probe(url, timeout=2.0):
            return True, ""

        if time.time() >= deadline:
            return False, "timeout"
        time.sleep(1.0)


# ---------------------------------------------------------------------------
# State file (v2 + v1 read compat)
# ---------------------------------------------------------------------------

def _load_state(cwd: Path) -> dict | None:
    state_path = cwd / STATE_FILE
    if not state_path.exists():
        return None
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if isinstance(raw, dict) and raw.get("version") == STATE_VERSION:
        return raw

    # v1 compat: top-level pid/port → wrap as single-service v2 (in memory only)
    if isinstance(raw, dict) and "pid" in raw and "port" in raw:
        port = int(raw.get("port", 3000))
        host = "localhost"
        scheme = "http"
        return {
            "version": STATE_VERSION,
            "profile": raw.get("profile"),
            "services": [{
                "name": "primary",
                "pid": int(raw["pid"]),
                "port": port,
                "host": host,
                "scheme": scheme,
                "command": raw.get("command", _DEFAULT_SERVICE["command"]),
                "url": f"{scheme}://{host}:{port}",
                "ready_path": _DEFAULT_SERVICE["ready_path"],
                "ready_timeout_seconds": _DEFAULT_SERVICE["ready_timeout_seconds"],
                "primary": True,
            }],
        }
    return None


def _save_state(cwd: Path, state: dict) -> None:
    """Non-atomic save (used for tests; production path uses _save_state_atomic)."""
    state_path = cwd / STATE_FILE
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _save_state_atomic(cwd: Path, state: dict) -> None:
    """Atomic save: write to <state>.tmp in the same dir, then os.replace."""
    final = cwd / STATE_FILE
    tmp = cwd / (STATE_FILE + ".tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(final))
    except OSError:
        # Best-effort cleanup of orphan tmp
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def _clear_state(cwd: Path) -> None:
    state_path = cwd / STATE_FILE
    if state_path.exists():
        try:
            state_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Per-service start/stop
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Already-running ownership check
# ---------------------------------------------------------------------------

def _already_running_owned(services: list[dict], state: dict | None) -> bool:
    """Strict ownership: every declared service's port is in use AND state's
    PIDs are all alive AND the state's service set matches the declared set."""
    if not state:
        return False
    state_services = {s["name"]: s for s in state.get("services", [])}
    if set(state_services.keys()) != {s["name"] for s in services}:
        return False
    for svc in services:
        rec = state_services.get(svc["name"])
        if not rec:
            return False
        if not _is_pid_running(rec.get("pid", 0)):
            return False
        port_open = any(
            _is_port_in_use_for_host(ph, svc["port"])
            for ph in _probe_hosts_for(svc.get("host", "localhost"))
        )
        if not port_open:
            return False
    return True


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

def _emit_warnings(warnings: list[str]) -> None:
    for w in warnings:
        print(f"[dev_server] {w}", file=sys.stderr)


def cmd_start(cwd: Path, profile: str | None) -> dict:
    """Resolve services from profile + start them. Backwards-compat entry point."""
    services, warnings = _get_services(profile, cwd)
    _emit_warnings(warnings)
    try:
        _validate_services(services)
    except ValueError as e:
        return {"running": False, "error": f"invalid services: {e}"}
    return cmd_start_with_services(cwd, services, profile=profile)


def cmd_start_with_services(
    cwd: Path, services: list[dict], profile: str | None
) -> dict:
    """Start an explicit (validated) list of services. No warnings emitted."""
    try:
        _validate_services(services)
    except ValueError as e:
        return {"running": False, "error": f"invalid services: {e}"}

    # Already-running ownership detection
    state = _load_state(cwd)
    if _already_running_owned(services, state):
        primary = _pick_primary(services)
        return {
            "running": True,
            "ready": True,
            "started_by_us": False,
            "pid": next(
                (s["pid"] for s in state["services"] if s["name"] == primary["name"]),
                None,
            ),
            "url": _service_url(primary),
            "services": state["services"],
            "message": "Dev server(s) already running",
        }

    # Stale state for a DIFFERENT service set with at least one PID still alive
    # → refuse rather than silently overwrite (would orphan our own previously-
    # tracked processes). Foreign processes are still never killed.
    if state and state.get("services"):
        declared_names = {svc["name"] for svc in services}
        state_names = {s["name"] for s in state["services"]}
        if state_names != declared_names:
            stale_alive = [
                rec for rec in state["services"]
                if _is_pid_running(rec.get("pid", 0))
            ]
            if stale_alive:
                stale_names = sorted(rec["name"] for rec in stale_alive)
                return {
                    "running": False,
                    "error": (
                        f"stale dev_server state for services {stale_names} "
                        f"with live PIDs; run 'dev_server.py stop' first"
                    ),
                    "services": [],
                }

    # Refuse to act if any port is busy without proven ownership
    for svc in services:
        for ph in _probe_hosts_for(svc.get("host", "localhost")):
            if _is_port_in_use_for_host(ph, svc["port"]):
                return {
                    "running": False,
                    "error": (
                        f"port {svc['port']} already in use (service {svc['name']!r}); "
                        f"run 'dev_server.py stop' or free the port manually"
                    ),
                    "services": [],
                }
        # don't kill, don't claim ownership

    # Topo-ordered start with rollback on failure
    layers = _topo_sort(services)
    started: list[tuple[Any, dict]] = []  # (proc, record)
    try:
        for layer in layers:
            # Popen all in this layer (cheap), then wait per-service
            spawned_in_layer: list[tuple[Any, dict, dict]] = []  # (proc, rec, svc)
            for svc in layer:
                proc, record = _start_one(svc, cwd)
                started.append((proc, record))
                spawned_in_layer.append((proc, record, svc))
            for proc, record, svc in spawned_in_layer:
                deadline = time.time() + int(svc.get("ready_timeout_seconds", 60))
                ok, reason = _wait_for_service(svc, proc, deadline)
                if not ok:
                    raise _StartFailed(svc["name"], reason)
        # All healthy → atomic state write
        state_to_save = {
            "version": STATE_VERSION,
            "profile": profile,
            "services": [rec for _, rec in started],
        }
        _save_state_atomic(cwd, state_to_save)
        primary_record = next(
            (rec for _, rec in started if rec.get("primary")),
            started[0][1] if started else None,
        )
        return {
            "running": True,
            "ready": True,
            "started_by_us": True,
            "pid": primary_record["pid"] if primary_record else None,
            "url": primary_record["url"] if primary_record else None,
            "services": [rec for _, rec in started],
        }
    except _StartFailed as e:
        return _rollback_and_report(started, error=str(e))
    except OSError as e:
        return _rollback_and_report(started, error=f"start error: {e}")


class _StartFailed(Exception):
    def __init__(self, service_name: str, reason: str):
        super().__init__(f"service {service_name!r} failed: {reason}")
        self.service_name = service_name
        self.reason = reason


def _rollback_and_report(
    started: list[tuple[Any, dict]], error: str
) -> dict:
    """Kill every started service in reverse, return error JSON. State already absent."""
    kill_results: list[dict] = []
    for proc, record in reversed(started):
        try:
            kill_results.append(_kill_one(record))
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


def cmd_stop(cwd: Path) -> dict:
    state = _load_state(cwd)
    if not state:
        return {"running": False, "message": "no dev server state"}
    services = state.get("services", [])
    results: list[dict] = []
    try:
        for record in reversed(services):
            try:
                results.append(_kill_one(record))
            except Exception as e:
                results.append({
                    "name": record.get("name"), "pid": record.get("pid"),
                    "killed": False, "reason": f"exception: {e}",
                })
    finally:
        _clear_state(cwd)
    return {"running": False, "services": list(reversed(results))}


def cmd_status(cwd: Path) -> dict:
    state = _load_state(cwd)
    if not state:
        return {"running": False, "message": "no dev server state"}
    services = state.get("services", [])
    per_service = []
    any_alive = False
    all_alive = True
    primary_record = None
    for rec in services:
        pid = rec.get("pid")
        port = rec.get("port")
        host = rec.get("host", "localhost")
        pid_alive = _is_pid_running(pid) if pid else False
        port_open = any(
            _is_port_in_use_for_host(ph, port)
            for ph in _probe_hosts_for(host)
        )
        per_alive = bool(pid_alive and port_open)
        any_alive = any_alive or per_alive
        all_alive = all_alive and per_alive
        per_service.append({
            **rec,
            "pid_alive": pid_alive,
            "port_in_use": port_open,
            "ready": per_alive,
        })
        if rec.get("primary"):
            primary_record = rec
    if primary_record is None and services:
        primary_record = services[0]

    if not any_alive:
        _clear_state(cwd)
        return {"running": False, "message": "no service alive; cleaned up state"}

    # Top-level pid/url reflect the primary IFF it's actually alive. If the
    # stack is partially up (running=False) but primary is dead, do not
    # advertise its pid/url — callers that read top-level keys would otherwise
    # think a usable URL exists.
    primary_alive = bool(
        primary_record
        and any(
            ps.get("ready") and ps.get("name") == primary_record.get("name")
            for ps in per_service
        )
    )
    primary_pid = primary_record.get("pid") if primary_alive else None
    primary_url = primary_record.get("url") if primary_alive else None
    return {
        "running": all_alive,
        "ready": all_alive,
        "pid": primary_pid,
        "url": primary_url,
        "services": per_service,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Manage target project dev server(s)")
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--cwd", required=True, help="Target project directory")
    parser.add_argument("--profile", help="Stack profile name (e.g., supabase-nextjs, vite-hono)")
    parser.add_argument(
        "--services-json",
        help="Inline services JSON array; takes precedence over --profile",
    )
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        print(json.dumps({"error": f"directory not found: {cwd}"}, indent=2))
        return 1

    if args.action == "start":
        if args.services_json:
            if args.profile:
                print(
                    "[dev_server] --services-json overrides --profile",
                    file=sys.stderr,
                )
            try:
                raw = json.loads(args.services_json)
            except json.JSONDecodeError as e:
                print(json.dumps({"running": False, "error": f"invalid --services-json: {e}"}, indent=2))
                return 2
            if not isinstance(raw, list):
                print(json.dumps({"running": False, "error": "--services-json must be a JSON array"}, indent=2))
                return 2
            try:
                services = [_normalize_service_entry(e) for e in raw]
            except (TypeError, AttributeError) as e:
                print(json.dumps({"running": False, "error": f"invalid services entry: {e}"}, indent=2))
                return 2
            try:
                _validate_services(services)
            except ValueError as e:
                print(json.dumps({"running": False, "error": str(e)}, indent=2))
                return 2
            result = cmd_start_with_services(cwd, services, profile=None)
        else:
            result = cmd_start(cwd, args.profile)
    elif args.action == "stop":
        result = cmd_stop(cwd)
    else:
        result = cmd_status(cwd)

    print(json.dumps(result, indent=2))
    return 0 if result.get("error") is None else 1


def main() -> int:
    return main_with_args(sys.argv[1:])


# ---------------------------------------------------------------------------
# Backwards-compat shims for legacy tests
# ---------------------------------------------------------------------------

def _get_config(profile: str | None, cwd: Path | None = None) -> dict:
    """Legacy: return a single-service config dict.

    Existing test_dev_server.py calls this with `_get_config("supabase-nextjs")`
    and expects keys like `command`, `port`. We honor the legacy contract by
    returning the dev_server block (or default).
    """
    if profile and profile in PROFILE_DEV_SERVERS:
        return dict(PROFILE_DEV_SERVERS[profile])
    if cwd:
        build_config = cwd / "shipwright_build_config.json"
        if build_config.exists():
            try:
                data = json.loads(build_config.read_text(encoding="utf-8"))
                dev_url = data.get("dev_url", "")
                if dev_url:
                    parsed = urlparse(dev_url)
                    port = parsed.port or 3000
                    return {
                        "command": _DEFAULT_SERVICE["command"],
                        "port": port,
                        "ready_timeout_seconds": _DEFAULT_SERVICE["ready_timeout_seconds"],
                        "ready_path": _DEFAULT_SERVICE["ready_path"],
                    }
            except (json.JSONDecodeError, OSError):
                pass
    return {
        "command": _DEFAULT_SERVICE["command"],
        "port": _DEFAULT_SERVICE["port"],
        "ready_timeout_seconds": _DEFAULT_SERVICE["ready_timeout_seconds"],
        "ready_path": _DEFAULT_SERVICE["ready_path"],
    }


def _wait_for_ready(port: int, timeout: int) -> bool:
    """Legacy: poll port until open or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if _is_port_in_use_for_host("127.0.0.1", port) or _is_port_in_use_for_host("::1", port):
            return True
        time.sleep(1)
    return False


if __name__ == "__main__":
    sys.exit(main())
