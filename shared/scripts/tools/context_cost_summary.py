#!/usr/bin/env python3
"""CLI: print a session's context-cost summary (written by the Stop hook).

Thin reader, no aggregation logic of its own — the ``Stop`` hook
(``track_context_cost.py``) already computed and wrote the per-session file
via ``context_cost_core.compute_summary``. This mirrors
``iterate_phase_timing.py summarize`` (print the pre-computed JSON; let the
caller format it): like that command, the iterate skill never invokes this
one automatically at a phase boundary — it is a manual, run-it-yourself CLI.
The one *automatic* surfacing this feature adds is the silent fold into
``work_completed.context_cost`` at F5b (see ``context_cost_core.fold_into_
event`` and ``F5b.md``); this command is for looking at the running total
without waiting for that.

Usage:
    uv run context_cost_summary.py show --project-root <p> --session-id <id>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.atomic_write import durable_read_text  # noqa: E402

_NO_DATA = {
    "calls": 0,
    "context_tokens": 0,
    "cost_usd": 0.0,
    "unpriced_calls": 0,
    "unpriced_models": [],
    "cost_complete": True,
    "by_phase": {},
    "no_data": True,
}

# A real Claude Code session id is a UUID. Membership in this allowlist -- not
# Path(session_id).name -- is the isolation guarantee: .name alone strips
# directory components (blocking traversal) but does NOT stop two distinct
# ids from collapsing onto the same basename (e.g. "other/victim" and
# "victim" both resolve to "victim.json"), which would let one session's
# write silently clobber another's file (external-review finding,
# iterate-2026-08-07-context-cost-meter). The single source of truth for
# this policy -- every writer (track_context_cost.py) and reader (this
# module, context_cost_statusline.py) calls THIS function, never its own
# copy.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def session_summary_path(project_root: Path, session_id: str | None) -> Path | None:
    """On-disk location of a session's summary, or ``None`` if the id is unsafe/absent."""
    if not isinstance(session_id, str) or not _SESSION_ID_RE.match(session_id):
        return None
    return project_root / ".shipwright" / "compliance" / "context-cost" / f"{session_id}.json"


def read_summary(project_root: Path, session_id: str | None) -> dict:
    path = session_summary_path(project_root, session_id)
    if path is None or not path.exists():
        return dict(_NO_DATA)
    try:
        data = json.loads(durable_read_text(path))
    except (ValueError, OSError):
        return dict(_NO_DATA)
    return data if isinstance(data, dict) else dict(_NO_DATA)


def read_and_fold_into_event(event: dict, project_root: Path, session_id: str) -> dict:
    """Read this session's summary and fold it into ``event`` (F5b caller).

    Convenience wrapper pairing :func:`read_summary` with
    :func:`context_cost_core.fold_into_event` for callers that only have a
    session id, not an already-read summary — same additive, best-effort
    contract as the fold itself (a missing/placeholder/malformed summary
    leaves ``event`` unchanged). Broad ``except`` matches
    ``iterate_phase_groups.fold_into_event``'s own precedent: this is a
    non-load-bearing nicety folded alongside the mandatory `work_completed`
    event at F5b, and must never be the reason that event is lost.
    """
    from lib.context_cost_core import fold_into_event

    if not session_id:
        print("[context_cost_summary] fold skipped: no session id", file=sys.stderr)
        return event
    try:
        summary = read_summary(project_root, session_id)
        if summary.get("no_data"):
            print(
                f"[context_cost_summary] fold skipped: no summary at "
                f"{session_summary_path(project_root, session_id)}",
                file=sys.stderr,
            )
            return event
        return fold_into_event(event, summary)
    except Exception as exc:  # noqa: BLE001 — must never break finalize
        print(f"[context_cost_summary] fold skipped: {exc}", file=sys.stderr)
        return event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a session's context-cost summary")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show", help="Print the per-session summary JSON")
    s.add_argument("--project-root", required=True)
    s.add_argument("--session-id", required=True)

    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()

    summary = read_summary(project_root, args.session_id)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
