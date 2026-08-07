#!/usr/bin/env python3
"""Claude Code statusLine.command script — one line of session cost/calls.

NOT auto-registered by anything in this repo. A plugin cannot write a user's
personal ``~/.claude/settings.json`` any more than it can set
``autoCompactWindow`` (see ``context_cost_readiness.py``) — an operator who
wants this in their status line points their own ``statusLine.command`` at
this script's path. Reads the per-session file
``context_cost_core.compute_summary`` already wrote via the ``Stop`` hook;
computes nothing itself.

Follows Claude Code's statusline contract: a JSON payload on stdin
(``session_id``, ``workspace.current_dir``, ...), one line of text on
stdout. Never raises — a broken statusline command breaks the whole prompt
line, so any failure here still prints *something* and exits 0.

Usage (wired manually into settings.json, not invoked by this repo):
    uv run context_cost_statusline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.context_cost_core import resolve_active_project_root, resolve_session_id  # noqa: E402
from tools.context_cost_summary import read_summary  # noqa: E402

_PLACEHOLDER = "context-cost: no data yet"


def _format(summary: dict) -> str:
    if summary.get("no_data"):
        return _PLACEHOLDER
    cost = summary.get("cost_usd", 0.0)
    calls = summary.get("calls", 0)
    suffix = "+" if not summary.get("cost_complete", True) else ""
    return f"context-cost: ${cost:.2f}{suffix} ({calls} calls)"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        # Same process class as the Stop hook (a subprocess Claude Code
        # spawns directly, not a Bash-tool child) — must resolve the session
        # id via the SAME function, or the reader looks in a different
        # session's file (or none) and silently prints the placeholder
        # forever. See context_cost_core.resolve_session_id's docstring.
        session_id = resolve_session_id(payload)
        workspace = payload.get("workspace") or {}
        cwd = workspace.get("current_dir") or workspace.get("project_dir") or "."
        # Same worktree-aware resolution as the writer (track_context_cost.py)
        # — during an active iterate, both must agree on the worktree the
        # Stop hook actually wrote to, or this silently shows the placeholder
        # forever. See resolve_active_project_root's docstring.
        project_root = resolve_active_project_root(Path(cwd).resolve(), session_id)
        summary = read_summary(project_root, session_id)
        print(_format(summary))
    except Exception:  # noqa: BLE001 — a broken statusline command breaks the prompt
        print(_PLACEHOLDER)

    return 0


if __name__ == "__main__":
    sys.exit(main())
