#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Iterate Stop hook -- keeps an ``--autonomous`` run going until it is delivered.

Blocks the Stop (top-level ``{"decision": "block", "reason": ...}``) while the
session's run pointer is live, i.e. before ``deliver_pr.py`` reached MERGED or
CLOSED. The decision logic lives in ``shared/scripts/lib/iterate_stop_guard.py``.
Fail-open on any error: this hook must never trap a session. Diagnostics go to
stderr; stdout carries the block JSON only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _find_shared_scripts() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"


sys.path.insert(0, str(_find_shared_scripts()))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        payload = {}
    if not isinstance(payload, dict) or os.environ.get("SHIPWRIGHT_LOOP_ID"):
        return 0  # campaign / loop units have their own DONE-marker sync
    session_id = str(payload.get("session_id") or os.environ.get("SHIPWRIGHT_SESSION_ID") or "")
    transcript = str(payload.get("transcript_path") or "")
    if not session_id or not transcript:
        return 0
    try:
        from lib import iterate_stop_guard as guard
        from lib.worktree_isolation import main_repo_root

        main_root = main_repo_root(Path.cwd())
        pointer = guard.live_pointer(main_root, session_id, transcript)
        if not pointer or not pointer.get("run_id"):
            return 0
        worktree = Path(str(pointer.get("worktree_path") or ""))
        if not worktree.is_dir():
            return 0
        run_id = str(pointer["run_id"])
        scan = guard.scan_transcript(transcript, guard.read_state(main_root, run_id, strict=True))
        autonomous = scan.autonomous
        reason = guard.decide(
            main_root=main_root, run_id=run_id, worktree=worktree,
            branch=str(pointer.get("branch") or ""), autonomous=autonomous,
            tool_count=scan.tools,
            scan={"autonomous": scan.autonomous, "tools": scan.tools, "offset": scan.offset,
                  "path": transcript, "reset": scan.reset},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[iterate_stop_guard] skipped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    if reason is None:
        try:
            blocker = guard.read_state(main_root, run_id).get("blocker")
            if blocker and autonomous:
                print(f"[iterate_stop_guard] stop allowed on recorded hard blocker "
                      f"{blocker['reason_code']}: {blocker['detail']}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
