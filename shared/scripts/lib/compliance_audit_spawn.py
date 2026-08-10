"""Spawn a `uv run` compliance-audit subprocess with a timeout that actually
bounds it (P2.59, branch-feedback authority; doubt review round 3, HIGH #1).

`subprocess.run(capture_output=True, timeout=...)` is not safe across a
`uv run` boundary: `uv` spawns its own child process for the target script
(no POSIX-style exec-replace on Windows), so the timeout handler's
`process.kill()` only kills `uv` itself, not that grandchild. Two failure
modes follow. On Windows, the post-kill code path calls `communicate()`
again to drain output — which blocks forever if the orphaned grandchild
still holds the inherited pipe write handle open, hanging `deliver_pr.py`
after a successful merge. On POSIX, `communicate()` doesn't re-block, but
the orphan keeps running unsupervised and can still converge the global
backlog after its caller has already recorded `{"ran": False}`.

Redirecting output to a file (not a pipe) removes the drain-blocks-forever
path, and killing the whole process TREE — not just the direct child —
removes the unsupervised-orphan path.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _kill_tree(pid: int) -> bool:
    """Best-effort. Returns whether the kill command itself reported success —
    NOT proof the tree is dead. The caller's own re-wait on the direct child is
    what actually confirms anything; a grandchild's death is never independently
    checked here. Never raises: a kill failure must not mask the timeout report
    (doubt review round 5 — a raising `_kill_tree` used to escape the caller's
    `except TimeoutExpired` entirely, skipping both the re-wait and the honest
    'not confirmed' detail)."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                    capture_output=True, timeout=30)
            return result.returncode == 0
        os.killpg(pid, 9)  # this IS the kill path — no graceful signal needed
        return True
    except (ProcessLookupError, PermissionError):
        return True  # already gone, or gone before the signal landed — not a failure
    except Exception:  # noqa: BLE001
        return False


def spawn_compliance_audit(argv: list[str], *, timeout: int = 180) -> dict:
    """Run ``argv`` (a ``uv run ...`` compliance-audit invocation).

    Returns ``{"ran": bool, "detail": str}`` — never raises.
    """
    popen_kwargs = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
        else {"start_new_session": True}
    )
    try:
        # `ignore_cleanup_errors`: if `_kill_tree` could not actually stop a
        # grandchild (e.g. `taskkill` denied, or a killpg race), it may still
        # hold `audit.out` open — cleanup must not raise over that (doubt
        # review round 4, MEDIUM).
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out_path = Path(tmp) / "audit.out"
            with out_path.open("w", encoding="utf-8") as out_fp:
                proc = subprocess.Popen(argv, stdout=out_fp, stderr=subprocess.STDOUT, **popen_kwargs)
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    kill_reported_ok = _kill_tree(proc.pid)
                    confirmed = False
                    try:
                        # Bounded even if the kill silently failed to land —
                        # this path exists precisely so a hung grandchild can
                        # never block the caller indefinitely.
                        proc.wait(timeout=30)
                        confirmed = True
                    except subprocess.TimeoutExpired:
                        pass
                    # A caller that reads "process tree killed" as proof the
                    # audit stopped must not be told that when it isn't true —
                    # a merge-authority audit that is still alive may still
                    # converge the global backlog after this returns ran=False
                    # (doubt review round 5).
                    status = ("process tree killed" if kill_reported_ok and confirmed
                             else "kill not confirmed")
                    return {"ran": False, "detail": f"audit timed out after {timeout}s ({status})"}
            detail = out_path.read_text(encoding="utf-8", errors="replace").strip()[:1000]
        return {"ran": proc.returncode == 0, "detail": detail or "no output"}
    except Exception as exc:  # noqa: BLE001 — a post-merge/release audit must never raise
        return {"ran": False, "detail": type(exc).__name__}
