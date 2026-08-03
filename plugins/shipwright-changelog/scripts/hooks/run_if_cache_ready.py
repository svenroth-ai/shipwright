#!/usr/bin/env python3
"""Run a later SessionStart hook only after its cache repair is complete."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from cache_repair_lock import (
        CACHE_LOCK_NAME,
        acquire_cache_read_lock,
        session_event_key,
        session_repair_state,
        unlock_cache_lock,
    )
except (ImportError, OSError, SyntaxError):
    CACHE_LOCK_NAME = ".sessionstart-cache-repair.lock"
    acquire_cache_read_lock = session_event_key = unlock_cache_lock = None
    session_repair_state = None

_READY_WAIT_SECONDS = 10.0


def _cache_ready(cache_root: Path) -> bool:
    """Read-only fallback for malformed/unavailable session coordination."""
    try:
        import ensure_shared_cache as healer
    except (ImportError, OSError, SyntaxError):
        return False
    shared = cache_root / "shared"
    if not healer._shared_healthy(shared):
        return False
    source = healer._same_name_shared(cache_root)
    if source is None or healer._incomplete(source, shared) is not False:
        return False
    enumeration: list[bool] = []
    for source, target in healer._plugin_mirrors(
        cache_root, cache_root / "plugins", enumeration,
    ):
        if target.is_symlink():
            if not healer._symlink_matches(source, target):
                return False
        elif healer._incomplete(source, target) is not False:
            return False
    return enumeration == [True]


def main() -> int:
    payload = sys.stdin.buffer.read()
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        decoded = {}
    plugin_root = Path(__file__).resolve().parents[2]
    cache_root = plugin_root.parent.parent
    dev_model = (cache_root / "scripts" / "update-marketplace.sh").is_file()
    event_key = "" if session_event_key is None else session_event_key(decoded)

    lock = None
    try:
        if len(sys.argv) < 2:
            print("shipwright: dependent hook target missing", file=sys.stderr)
            return 0
        targets = [Path(arg) for arg in sys.argv[1:]]
        if not dev_model:
            try:
                import ensure_shared_cache as healer
            except (ImportError, OSError, SyntaxError):
                healer = None
            plugin_id = plugin_root.name if plugin_root.name.startswith(
                "shipwright-",
            ) else plugin_root.parent.name
            participant = f"{plugin_id}:sessionstart"
            if healer is not None:
                healer.main(decoded, participant)
            deadline = time.monotonic() + _READY_WAIT_SECONDS
            coordinated = bool(event_key) and event_key != "unknown"
            state = None
            while coordinated and session_repair_state is not None:
                state = session_repair_state(cache_root, event_key)
                if state is not False or time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            lock = None if acquire_cache_read_lock is None else acquire_cache_read_lock(
                cache_root / CACHE_LOCK_NAME,
            )
            if lock is None:
                print("shipwright: cache writer active; dependent hook skipped",
                      file=sys.stderr)
                return 0
            state = session_repair_state(cache_root, event_key) \
                if coordinated and session_repair_state is not None else None
            if state is not True and not (state is None and _cache_ready(cache_root)):
                print("shipwright: cache repair not ready; dependent hook skipped",
                      file=sys.stderr)
                return 0

        return_code = 0
        contexts: list[str] = []
        for target in targets:
            if not target.is_file():
                print(f"shipwright: dependent hook unavailable: {target}",
                      file=sys.stderr)
                continue
            completed = subprocess.run(
                [sys.executable, str(target)], input=payload,
                capture_output=True, check=False,
            )
            if completed.stderr:
                sys.stderr.buffer.write(completed.stderr)
                sys.stderr.buffer.flush()
            if completed.stdout.strip():
                try:
                    result = json.loads(completed.stdout)
                    if not isinstance(result, dict):
                        raise TypeError("hook result must be an object")
                    specific = result.get("hookSpecificOutput")
                    if not isinstance(specific, dict):
                        raise TypeError("hookSpecificOutput must be an object")
                    if specific.get("hookEventName") != "SessionStart":
                        raise ValueError("wrong hookEventName")
                    context = specific.get("additionalContext")
                    if not isinstance(context, str):
                        raise TypeError("additionalContext must be a string")
                    if context:
                        contexts.append(context)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    print(f"shipwright: invalid SessionStart output skipped: {target}",
                          file=sys.stderr)
            if not return_code:
                return_code = completed.returncode
        if contexts:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(contexts),
            }}))
        return return_code
    finally:
        if lock is not None:
            descriptor = lock[0] if isinstance(lock, tuple) else lock
            try:
                unlock_cache_lock(lock)
            finally:
                os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
