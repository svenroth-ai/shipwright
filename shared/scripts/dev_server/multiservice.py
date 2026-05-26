"""Top-level dev_server commands: start, stop, status (multi-service aware).

Extracted from `shared/scripts/dev_server.py` during B4 split (campaign
`2026-05-25-bloat-cleanup-B-shipwright`). Producer/consumer surface
preserved via package-level re-exports in `__init__.py`.

Composition order:
  cmd_start → _get_services (profile_config)
            → _validate_services (validation)
            → _load_state (state) [already-running check]
            → _topo_sort (validation)
            → _start_one + _wait_for_service (spawn + health) per layer
            → _save_state_atomic (state) iff all healthy
            → _rollback_and_report (spawn) on failure
  cmd_stop  → _load_state → _kill_one per service in reverse → _clear_state
  cmd_status→ _load_state → liveness check per service via spawn + health
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

# Internal proxies that look up names on the package surface at call time
# so test monkeypatches (`@patch("dev_server._is_port_in_use_for_host")`)
# propagate into the multi-service code paths.
from ._proxies import (
    _clear_state,
    _is_pid_running,
    _is_port_in_use_for_host,
    _kill_one,
    _load_state,
    _probe_hosts_for,
    _rollback_and_report,
    _save_state_atomic,
    _start_one,
    _wait_for_service,
)
from .profile_config import STATE_VERSION, _get_services
from .spawn import _StartFailed
from .validation import _pick_primary, _topo_sort, _validate_services


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

    # Need _service_url for response payloads; import lazily to avoid a
    # cyclic dependency (profile_config does not import this module).
    from .profile_config import _service_url

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
