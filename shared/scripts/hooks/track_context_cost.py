#!/usr/bin/env python3
"""Stop hook: measure this session's actual API cost from its own transcript.

Additive — registered alongside the existing ``track_tool_calls.py`` /
``generate_handoff_on_stop.py`` Stop-array entries, never replacing them
(context-cost-meter, per operator instruction: land the measurement first,
cut the old tool-call-count proxy over only later, once real data exists to
compare the two against).

On every firing this reads the FULL transcript and recomputes the session's
summary from scratch — no incremental cache, nothing to keep in sync across
a crash (sessions are small, median ~276 calls, so a full re-read is cheap;
see ``shared/scripts/lib/context_cost_core.py`` for why the incremental
design this replaced was rejected in external review). The result overwrites
one JSON file per session, so concurrent sessions/worktrees never contend on
the same file.

Usage (from hooks.json):
    uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/track_context_cost.py"

Never blocks session shutdown: every failure is caught, logged to stderr,
and the hook still returns 0 — matching ``generate_handoff_on_stop.py``'s
own contract. Prints nothing to stdout (Stop hooks may not carry
``hookSpecificOutput``; see ``test_hook_output_schema_compliance.py``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.context_cost_core import (  # noqa: E402
    compute_summary,
    resolve_active_project_root,
    resolve_session_id,
)
from lib.phase_quality import pointer_run_id  # noqa: E402
from lib.project_root import is_shipwright_project  # noqa: E402
from tools.context_cost_summary import session_summary_path  # noqa: E402


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # payload["session_id"] first, SHIPWRIGHT_SESSION_ID only as fallback —
    # this hook runs as a Claude-Code-spawned Stop subprocess, the same
    # process class documented in bloat_gate_on_stop.py's own _session_id
    # docstring as NOT reliably inheriting that env var (fixed 2026-05-29
    # after env-first pooled every session into one shared file). See
    # context_cost_core.resolve_session_id's docstring for the full writer/
    # reader contract this shares with context_cost_statusline.py.
    session_id = resolve_session_id(payload)
    if not session_id:
        # Neither the payload nor the env var had a real id -- writing under
        # a fixed placeholder name would pool every such firing into one
        # shared file, exactly the failure class this whole payload-first
        # design exists to avoid (external-review finding,
        # iterate-2026-08-07-context-cost-meter). Skip rather than guess.
        sys.stderr.write("[shipwright:context-cost] measurement skipped: no session id available\n")
        return 0

    # Worktree-aware: a Stop subprocess's cwd is the MAIN repo even while an
    # iterate runs in a linked worktree, and this session id is what maps to
    # that worktree via the active-run pointer. See resolve_active_project_
    # root's docstring for why the naive resolver silently missed this (doubt-
    # review finding, iterate-2026-08-07-context-cost-meter).
    project_root = resolve_active_project_root(Path.cwd(), session_id)

    if not is_shipwright_project(project_root):
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0

    # A missing transcript file is not "zero calls" -- compute_summary
    # would happily return an empty-but-valid-shaped summary for it, and
    # writing THAT would silently destroy this session's already-recorded
    # cost data on the very next Stop after a transient path/race issue.
    # Treat it as "nothing new to measure this firing" instead: skip the
    # write and leave whatever was last durably recorded in place
    # (external-review finding, iterate-2026-08-07-context-cost-meter).
    if not Path(transcript_path).exists():
        sys.stderr.write(
            f"[shipwright:context-cost] measurement skipped: transcript not found at {transcript_path}\n"
        )
        return 0

    # pointer_run_id, not the full resolve_run_id fallback chain and not the
    # raw SHIPWRIGHT_RUN_ID env var (a hook-launched subprocess never inherits
    # the skill's shell export — docs/hooks-and-pipeline.md's C3 section;
    # rejected explicitly for this reason in iterate-2026-08-06-resolve-run-
    # id-seam, shipped the day before this feature). pointer_run_id is the
    # ONE source scoped to "which run is THIS session executing" (live,
    # session-matched, self-pruning); resolve_run_id's other fallbacks
    # (shipwright_run_config.json, latest run_started event) are project-
    # global and can outlive the run that minted them — feeding one of those
    # here would attribute a call to a stale run's gitignored-but-still-on-
    # disk phase marks sidecar, since _resolve_phase only guards the
    # before-first-mark direction (doubt-review finding,
    # iterate-2026-08-07-context-cost-meter). None here means "no iterate is
    # active for this session", which correctly degrades every call to
    # "unphased" rather than misattributing them.
    run_id = pointer_run_id(project_root, session_id)

    out_path = session_summary_path(project_root, session_id)
    if out_path is None:
        sys.stderr.write(
            f"[shipwright:context-cost] measurement skipped: unsafe session id {session_id!r}\n"
        )
        return 0

    try:
        summary = compute_summary(transcript_path, project_root, run_id=run_id)
        durable_atomic_write(out_path, json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001 — must never block session shutdown
        sys.stderr.write(f"[shipwright:context-cost] measurement skipped: {type(exc).__name__}: {exc}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
