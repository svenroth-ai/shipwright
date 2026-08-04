"""Fair cross-process weighted leases shared by sibling Git worktrees.

The mutable JSON is only an admission index.  Liveness comes from a byte-range
lock held on each ticket: process death releases that lock, so reclaim never
depends on PID age or deleting a stale lock file.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import subprocess  # nosec B404 - fixed git argv, shell=False
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TextIO
from uuid import uuid4

from scripts.lib._host_resource_locking import (
    HostLeaseError, _forget_owner_ticket, _mutex, _new_owner_lock, _probe_dead,
    _posix_shared_temp_root, _safe_dir, _safe_file, _safe_runtime_root, _unlock_byte,
)

_RESOURCE = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
_VERSION = 1

@dataclass(frozen=True)
class LeaseGrant:
    weight: int
    capacity: int
    ticket: str
    waited_seconds: float

def repository_identity(project_root: Path) -> str:
    """Hash the resolved Git common directory; sibling worktrees converge."""
    root = Path(project_root).resolve()
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute",
             "--git-common-dir"], capture_output=True, text=True, errors="replace",
            shell=False, timeout=10, check=False, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise HostLeaseError(f"could not resolve repository identity for {root}") from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise HostLeaseError(f"could not resolve repository identity for {root}")
    subject = Path(proc.stdout.strip()).resolve()
    value = os.path.normcase(str(subject)) if os.name == "nt" else str(subject)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _private_location() -> tuple[Path, Path, bool]:
    allow_sticky_shared = False
    if os.name == "nt":
        if not os.environ.get("LOCALAPPDATA"):
            raise HostLeaseError("LOCALAPPDATA is required for the Windows lease root")
        anchor = Path(os.environ["LOCALAPPDATA"])
        base = anchor / "Shipwright"
    elif os.environ.get("XDG_RUNTIME_DIR"):
        anchor = Path(os.environ["XDG_RUNTIME_DIR"])
        base = anchor / "shipwright"
    else:
        uid = str(os.getuid()) if hasattr(os, "getuid") else getpass.getuser()
        anchor = _posix_shared_temp_root()
        for name in ("TMPDIR", "TEMP", "TMP"):
            override = os.environ.get(name)
            if override and Path(override).resolve() != anchor:
                raise HostLeaseError(
                    f"untrusted {name} cannot select the host lease runtime root")
        base = anchor / f"shipwright-{uid}"
        allow_sticky_shared = True
    return base / "host-leases-v1", anchor, allow_sticky_shared


def _private_root() -> Path:
    return _private_location()[0]

def _load(path: Path, capacity: int) -> dict:
    if not path.exists():
        return {"version": _VERSION, "capacity": capacity, "next_seq": 1, "entries": []}
    _safe_file(path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HostLeaseError(f"malformed host lease state {path}: {exc}") from exc
    if (not isinstance(state, dict) or state.get("version") != _VERSION
            or not isinstance(state.get("next_seq"), int)
            or isinstance(state.get("next_seq"), bool) or state["next_seq"] < 1
            or not isinstance(state.get("entries"), list)
            or not isinstance(state.get("capacity"), int)
            or isinstance(state.get("capacity"), bool) or state["capacity"] < 1):
        raise HostLeaseError(f"malformed host lease state {path}: invalid shape")
    stored_capacity = state["capacity"]
    seen_tickets, seen_sequences = set(), set()
    for entry in state["entries"]:
        valid = (
            isinstance(entry, dict)
            and isinstance(entry.get("ticket"), str)
            and re.fullmatch(r"[0-9a-f]{32}", entry["ticket"])
            and isinstance(entry.get("seq"), int) and not isinstance(entry["seq"], bool)
            and entry["seq"] > 0
            and isinstance(entry.get("weight"), int)
            and not isinstance(entry["weight"], bool)
            and 1 <= entry["weight"] <= stored_capacity
            and entry.get("status") in {"waiting", "granted"}
            and isinstance(entry.get("owner"), str)
            and isinstance(entry.get("run_id"), str)
            and isinstance(entry.get("pid"), int) and not isinstance(entry["pid"], bool)
            and entry["pid"] > 0
        )
        if not valid:
            raise HostLeaseError(f"malformed host lease state {path}: invalid entry")
        if entry["ticket"] in seen_tickets or entry["seq"] in seen_sequences:
            raise HostLeaseError(f"malformed host lease state {path}: duplicate entry")
        seen_tickets.add(entry["ticket"])
        seen_sequences.add(entry["seq"])
    if seen_sequences and state["next_seq"] <= max(seen_sequences):
        raise HostLeaseError(f"malformed host lease state {path}: invalid sequence")
    granted = sum(entry["weight"] for entry in state["entries"]
                  if entry["status"] == "granted")
    if granted > stored_capacity:
        raise HostLeaseError(f"malformed host lease state {path}: capacity exceeded")
    return state


def _adopt_capacity(state: dict, capacity: int) -> bool:
    if state["capacity"] == capacity:
        return False
    if state["entries"]:
        raise HostLeaseError(
            f"host lease capacity changed while leases are live: "
            f"{state['capacity']} -> {capacity}")
    state["capacity"] = capacity
    return True


def _write(path: Path, state: dict) -> None:
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(state, sort_keys=True, ensure_ascii=False) + "\n")
        if os.name != "nt":
            tmp.chmod(0o600)
        _safe_file(tmp)
        os.replace(tmp, path)
        _safe_file(path)
    except OSError as exc:
        raise HostLeaseError(f"could not update host lease state {path}: {exc}") from exc
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _reap(state: dict, tickets: Path, own_ticket: str) -> bool:
    kept, changed = [], False
    for entry in state["entries"]:
        ticket = entry.get("ticket") if isinstance(entry, dict) else None
        if not isinstance(ticket, str):
            raise HostLeaseError("malformed host lease entry")
        if ticket != own_ticket and _probe_dead(tickets / f"{ticket}.owner.lock"):
            changed = True
            continue
        kept.append(entry)
    state["entries"] = kept
    return changed


def _clean(value: object) -> str:
    text = " ".join(str(value or "-").split())[:200]
    return text.encode("ascii", "backslashreplace").decode("ascii")


def _diagnostic(kind: str, *, resource: str, run_id: str | None, owner: str,
                blocker: dict | None, used: int, capacity: int, waited: float) -> str:
    return (f"F0 host lease {kind}: resource={resource} run_id={_clean(run_id)} "
            f"owner={_clean(owner)} queue_owner={_clean((blocker or {}).get('owner'))} "
            f"queue_run_id={_clean((blocker or {}).get('run_id'))} "
            f"used={used}/{capacity} waited={waited:.1f}s")


def _emit_diagnostic(stream: TextIO, line: str) -> None:
    try:
        print(line, file=stream, flush=True)
    except (OSError, ValueError):
        pass


@contextmanager
def host_resource_lease(project_root: Path, *, resource: str, capacity: int,
                        weight: int, owner: str, run_id: str | None = None,
                        heartbeat_seconds: float = 30.0, poll_seconds: float = 0.1,
                        stream: TextIO | None = None,
                        lease_root: Path | None = None) -> Iterator[LeaseGrant]:
    """Acquire a strict-FIFO weighted lease and release it on every normal exit."""
    if not _RESOURCE.fullmatch(resource):
        raise HostLeaseError(f"invalid host resource name: {resource!r}")
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise HostLeaseError(f"capacity must be a positive integer, got {capacity!r}")
    if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= capacity:
        raise HostLeaseError(f"weight must be within 1..{capacity}, got {weight!r}")
    output = stream if stream is not None else sys.stderr
    if lease_root is None:
        base, trusted_parent, allow_sticky_shared = _private_location()
    else:
        base = Path(lease_root)
        trusted_parent = base.parent
        allow_sticky_shared = False
    _safe_runtime_root(trusted_parent, allow_sticky_shared=allow_sticky_shared)
    _safe_dir(base, trusted_parent=trusted_parent)
    namespace = base / repository_identity(project_root)
    _safe_dir(namespace, trusted_parent=trusted_parent)
    tickets = namespace / "tickets"
    _safe_dir(tickets, trusted_parent=trusted_parent)
    state_path, mutex_path = namespace / f"{resource}.state.json", namespace / f"{resource}.mutex.lock"
    ticket = uuid4().hex
    ticket_path = None
    owner_handle = None
    state_removed = False
    started = time.monotonic()
    try:
        with _mutex(mutex_path):
            state = _load(state_path, capacity)
            _reap(state, tickets, ticket)
            _adopt_capacity(state, capacity)
            ticket_path, owner_handle = _new_owner_lock(tickets, ticket)
            seq = state["next_seq"]
            state["next_seq"] += 1
            state["entries"].append({"ticket": ticket, "seq": seq, "weight": weight,
                                     "owner": _clean(owner), "run_id": _clean(run_id),
                                     "pid": os.getpid(), "status": "waiting"})
            _write(state_path, state)

        announced = False
        next_heartbeat = started + max(0.01, heartbeat_seconds)
        while True:
            blocker = None
            with _mutex(mutex_path):
                state = _load(state_path, capacity)
                changed = _reap(state, tickets, ticket)
                changed = _adopt_capacity(state, capacity) or changed
                own = next((e for e in state["entries"] if e["ticket"] == ticket), None)
                if own is None:
                    raise HostLeaseError(f"live ticket disappeared from state: {ticket}")
                granted = [e for e in state["entries"] if e.get("status") == "granted"]
                waiting = sorted((e for e in state["entries"] if e.get("status") == "waiting"),
                                 key=lambda e: e["seq"])
                used = sum(int(e["weight"]) for e in granted)
                if waiting and waiting[0]["ticket"] == ticket and used + weight <= capacity:
                    own["status"] = "granted"
                    _write(state_path, state)
                    break
                ahead = [e for e in waiting if e["seq"] < own["seq"]]
                blocker = ahead[0] if ahead else (granted[0] if granted else waiting[0])
                if changed:
                    _write(state_path, state)
            now = time.monotonic()
            if not announced or now >= next_heartbeat:
                kind = "waiting" if not announced else "heartbeat"
                _emit_diagnostic(
                    output,
                    _diagnostic(kind, resource=resource, run_id=run_id, owner=owner,
                                blocker=blocker, used=used, capacity=capacity,
                                waited=now - started),
                )
                announced = True
                next_heartbeat = now + max(0.01, heartbeat_seconds)
            time.sleep(max(0.01, poll_seconds))

        yield LeaseGrant(weight, capacity, ticket, time.monotonic() - started)
    finally:
        if owner_handle is not None:
            try:
                with _mutex(mutex_path):
                    state = _load(state_path, capacity)
                    state["entries"] = [e for e in state["entries"] if e.get("ticket") != ticket]
                    _write(state_path, state)
                    state_removed = True
            finally:
                try:
                    if ticket_path is not None:
                        _forget_owner_ticket(ticket_path)
                    _unlock_byte(owner_handle)
                finally:
                    owner_handle.close()
        if ticket_path is not None and state_removed:
            try:
                ticket_path.unlink(missing_ok=True)
            except OSError:
                pass
