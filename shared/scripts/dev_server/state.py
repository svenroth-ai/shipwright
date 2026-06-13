"""State-file IO (v1 read-compat + v2 atomic write).

Extracted from `shared/scripts/dev_server.py` during B4 split (campaign
`2026-05-25-bloat-cleanup-B-shipwright`). The file at
`<cwd>/shipwright_dev_server.json` is the producer/consumer boundary
between `cmd_start` (writes after all services healthy) and `cmd_stop`
/ `cmd_status` (read to find PIDs to kill / report). The v1→v2
read-compat path supports legacy state files written by pre-multi-service
dev_server versions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .profile_config import _DEFAULT_SERVICE, STATE_FILE, STATE_VERSION

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402


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
    """Durable atomic save (tmp + fsync + os.replace via the shared
    :func:`durable_atomic_write`)."""
    durable_atomic_write(cwd / STATE_FILE, json.dumps(state, indent=2) + "\n")


def _clear_state(cwd: Path) -> None:
    state_path = cwd / STATE_FILE
    if state_path.exists():
        try:
            state_path.unlink()
        except OSError:
            pass
