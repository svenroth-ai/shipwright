#!/usr/bin/env python3
"""Estimate context window pressure from tool call count (default) or
measured API cost (opt-in).

Default source reads .shipwright/toolcall_count (plain integer file) and
returns a recommendation on whether to checkpoint. The opt-in
``--source context-cost`` mode reads the CURRENT session's context-cost
summary (context-cost-meter, `.shipwright/compliance/context-cost/
<session_id>.json`, written by the `track_context_cost.py` Stop hook)
instead, compared against the SAME two thresholds — it does not replace
the default, only offers it as an alternative signal until real data
exists to compare the two against (retiring the toolcall proxy is an
explicit follow-up iterate).

Usage:
    uv run estimate_context_pressure.py [--counter-file <path>] [--threshold <n>] [--mode <mode>]
    uv run estimate_context_pressure.py --source context-cost [--threshold <n>] [--mode <mode>]

Modes:
    builder (default): threshold 120 — used within /shipwright-build (guided mode)
    orchestrator:      threshold 300 — used by /shipwright-run when delegating to subagents

Output (JSON), source=toolcall (default):
    {"tool_calls": 142, "threshold": 120, "recommend_checkpoint": true, "mode": "builder",
     "source": "toolcall"}

Output (JSON), source=context-cost:
    {"tool_calls": 142, "threshold": 120, "recommend_checkpoint": true, "mode": "builder",
     "source": "context-cost", "cost_usd": 4.12, "cost_complete": true, "no_data": false}
"""

import argparse
import json
import os
import sys
from pathlib import Path


MODE_THRESHOLDS = {
    "builder": 120,
    "orchestrator": 300,
}


def _resolve_project_root() -> Path:
    """Resolve the project root the SAME way the producer (track_tool_calls)
    does — via ``resolve_project_root()``, which auto-descends into a managed
    subdirectory.

    F10: the readers previously used ``os.environ/Path.cwd()`` only, so in an
    auto-descent layout the producer incremented ``<subdir>/.shipwright/…`` while
    the reader looked at ``<workspace>/.shipwright/…`` (never created) → count 0
    → context-pressure checkpointing silently dead.
    """
    try:
        shared_scripts = str(Path(__file__).resolve().parent.parent)
        if shared_scripts not in sys.path:
            sys.path.insert(0, shared_scripts)
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return resolve_project_root()
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return Path(env_root) if env_root else Path.cwd()


def estimate_pressure(counter_file: Path, threshold: int, mode: str = "builder") -> dict:
    """Read counter file and compute pressure recommendation."""
    tool_calls = 0
    if counter_file.exists():
        try:
            tool_calls = int(counter_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            tool_calls = 0

    return {
        "tool_calls": tool_calls,
        "threshold": threshold,
        "recommend_checkpoint": tool_calls >= threshold,
        "mode": mode,
        "source": "toolcall",
    }


def estimate_pressure_context_cost(project_root: Path, threshold: int, mode: str = "builder") -> dict:
    """Read the CURRENT session's context-cost summary and compute pressure.

    Session-scoped, not run-scoped: a context window resets per Claude Code
    session, not per iterate run (a resumable run can span several
    sessions), so this reads only ``<SHIPWRIGHT_SESSION_ID>.json``, never
    another session's file.

    Keyed by ``SHIPWRIGHT_SESSION_ID`` alone — this is a plain Bash-tool-
    invoked script, not a subprocess Claude Code spawns directly, so it has
    no stdin payload and (unlike the ``Stop`` hook / statusline) reliably
    inherits the env var via ``CLAUDE_ENV_FILE`` (see
    ``context_cost_core.resolve_session_id``'s docstring for the full
    writer/reader contract by process class). ``calls`` is reported under
    the same ``tool_calls`` key as the toolcall source so callers can compare
    against ``threshold`` source-agnostically; ``source``, ``cost_usd``,
    ``cost_complete`` and ``no_data`` are additive.
    """
    shared_scripts = str(Path(__file__).resolve().parent.parent)
    if shared_scripts not in sys.path:
        sys.path.insert(0, shared_scripts)
    from tools.context_cost_summary import read_summary  # noqa: PLC0415

    # No "unknown" placeholder fallback: a fixed name would pool every
    # session missing this env var into one shared file -- the same
    # collision class context_cost_session.resolve_session_id's own
    # docstring rules out for the Stop-hook process class (external-review
    # finding, iterate-2026-08-07-context-cost-meter). read_summary already
    # degrades a falsy/None session id to its no-data default.
    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID")
    summary = read_summary(project_root, session_id)
    tool_calls = summary.get("calls", 0)

    return {
        "tool_calls": tool_calls,
        "threshold": threshold,
        "recommend_checkpoint": tool_calls >= threshold,
        "mode": mode,
        "source": "context-cost",
        "cost_usd": summary.get("cost_usd", 0.0),
        "cost_complete": summary.get("cost_complete", True),
        "no_data": bool(summary.get("no_data", False)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate context pressure")
    parser.add_argument(
        "--counter-file",
        default=".shipwright/toolcall_count",
        help="Path to tool call counter file (default: .shipwright/toolcall_count in cwd)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Tool call threshold for checkpoint recommendation (default: mode-dependent)",
    )
    parser.add_argument(
        "--mode",
        choices=list(MODE_THRESHOLDS.keys()),
        default="builder",
        help="Execution mode: 'builder' (120, default) or 'orchestrator' (300)",
    )
    parser.add_argument(
        "--source",
        choices=["toolcall", "context-cost"],
        default="toolcall",
        help="'toolcall' (default, unchanged) or 'context-cost' (opt-in, "
             "reads the current session's measured-cost summary instead)",
    )
    args = parser.parse_args()

    threshold = args.threshold if args.threshold is not None else MODE_THRESHOLDS[args.mode]

    if args.source == "context-cost":
        result = estimate_pressure_context_cost(_resolve_project_root(), threshold, args.mode)
    else:
        counter_file = Path(args.counter_file)
        if not counter_file.is_absolute():
            counter_file = _resolve_project_root() / counter_file
        result = estimate_pressure(counter_file, threshold, args.mode)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
