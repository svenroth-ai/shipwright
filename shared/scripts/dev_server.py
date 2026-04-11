#!/usr/bin/env python3
"""Start/Stop/Status management for the target project's dev server.

Usage:
    uv run dev_server.py start --profile supabase-nextjs --cwd /path/to/project
    uv run dev_server.py stop --cwd /path/to/project
    uv run dev_server.py status --cwd /path/to/project

Output (JSON):
    {"running": true, "pid": 12345, "url": "http://localhost:3000", "ready": true}
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# Default dev server config (used if profile doesn't specify)
DEFAULT_DEV_SERVER = {
    "command": "npm run dev",
    "port": 3000,
    "ready_timeout_seconds": 60,
    "ready_path": "/",
}

# Profile-specific overrides
PROFILE_DEV_SERVERS: dict[str, dict] = {
    "supabase-nextjs": {
        "command": "npm run dev",
        "port": 3000,
        "ready_timeout_seconds": 60,
        "ready_path": "/",
    },
}

STATE_FILE = "shipwright_dev_server.json"


def _is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _is_pid_running(pid: int) -> bool:
    """Check if a process with given PID is still running."""
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
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _load_state(cwd: Path) -> dict | None:
    """Load dev server state from file."""
    state_path = cwd / STATE_FILE
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_state(cwd: Path, state: dict) -> None:
    """Save dev server state to file."""
    state_path = cwd / STATE_FILE
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _clear_state(cwd: Path) -> None:
    """Remove state file."""
    state_path = cwd / STATE_FILE
    if state_path.exists():
        state_path.unlink()


def _get_config(profile: str | None, cwd: Path | None = None) -> dict:
    """Get dev server config for profile.

    Falls back to shipwright_build_config.json for custom/unknown profiles.
    """
    if profile and profile in PROFILE_DEV_SERVERS:
        return PROFILE_DEV_SERVERS[profile]
    # Try build config for custom profiles (self-healing)
    if cwd:
        build_config = cwd / "shipwright_build_config.json"
        if build_config.exists():
            try:
                data = json.loads(build_config.read_text(encoding="utf-8"))
                dev_url = data.get("dev_url", "")
                if dev_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(dev_url)
                    port = parsed.port or 3000
                    return {**DEFAULT_DEV_SERVER, "port": port}
            except (json.JSONDecodeError, OSError):
                pass
    return DEFAULT_DEV_SERVER


def _wait_for_ready(port: int, timeout: int) -> bool:
    """Poll until the server is accepting connections on the port."""
    start = time.time()
    while time.time() - start < timeout:
        if _is_port_in_use(port):
            return True
        time.sleep(1)
    return False


def cmd_start(cwd: Path, profile: str | None) -> dict:
    """Start the dev server."""
    config = _get_config(profile, cwd=cwd)
    port = config["port"]
    timeout = config["ready_timeout_seconds"]

    # Check if already running
    if _is_port_in_use(port):
        state = _load_state(cwd)
        pid = state.get("pid") if state else None
        return {
            "running": True,
            "pid": pid,
            "url": f"http://localhost:{port}",
            "ready": True,
            "message": f"Dev server already running on port {port}",
            "started_by_us": False,
        }

    # Start the dev server
    cmd_parts = config["command"].split()
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        proc = subprocess.Popen(
            cmd_parts,
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except OSError as e:
        return {
            "running": False,
            "error": f"Failed to start dev server: {e}",
            "command": config["command"],
        }

    # Save state
    _save_state(cwd, {
        "pid": proc.pid,
        "port": port,
        "command": config["command"],
        "profile": profile,
    })

    # Wait for ready
    ready = _wait_for_ready(port, timeout)

    return {
        "running": ready,
        "pid": proc.pid,
        "url": f"http://localhost:{port}",
        "ready": ready,
        "message": "Dev server started" if ready else f"Dev server started but not ready after {timeout}s",
        "started_by_us": True,
    }


def cmd_stop(cwd: Path) -> dict:
    """Stop the dev server."""
    state = _load_state(cwd)
    if not state:
        return {"running": False, "message": "No dev server state found"}

    pid = state.get("pid")
    if not pid:
        _clear_state(cwd)
        return {"running": False, "message": "No PID in state file"}

    if not _is_pid_running(pid):
        _clear_state(cwd)
        return {"running": False, "message": f"Process {pid} not running, cleaned up state"}

    # Kill the process
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
            # Wait briefly for graceful shutdown
            time.sleep(2)
            if _is_pid_running(pid):
                os.kill(pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        pass

    _clear_state(cwd)
    return {"running": False, "pid": pid, "message": f"Dev server (PID {pid}) stopped"}


def cmd_status(cwd: Path) -> dict:
    """Check dev server status."""
    state = _load_state(cwd)
    if not state:
        return {"running": False, "message": "No dev server state"}

    pid = state.get("pid")
    port = state.get("port", 3000)

    pid_alive = _is_pid_running(pid) if pid else False
    port_in_use = _is_port_in_use(port)

    if not pid_alive and not port_in_use:
        _clear_state(cwd)
        return {"running": False, "message": "Dev server not running, cleaned up stale state"}

    return {
        "running": port_in_use,
        "pid": pid,
        "url": f"http://localhost:{port}",
        "ready": port_in_use,
        "pid_alive": pid_alive,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage target project dev server")
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--cwd", required=True, help="Target project directory")
    parser.add_argument("--profile", help="Stack profile name (e.g., supabase-nextjs)")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        print(json.dumps({"error": f"Directory not found: {cwd}"}, indent=2))
        return 1

    if args.action == "start":
        result = cmd_start(cwd, args.profile)
    elif args.action == "stop":
        result = cmd_stop(cwd)
    else:
        result = cmd_status(cwd)

    print(json.dumps(result, indent=2))
    return 0 if result.get("error") is None else 1


if __name__ == "__main__":
    sys.exit(main())
