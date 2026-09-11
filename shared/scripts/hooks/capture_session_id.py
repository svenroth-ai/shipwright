#!/usr/bin/env python3
"""Canonical SessionStart hook for all Shipwright plugins.

Injects Shipwright environment variables into Claude's session context:
- SHIPWRIGHT_SESSION_ID: current session id (from hook payload)
- SHIPWRIGHT_PLUGIN_ROOT: active plugin directory (from CLAUDE_PLUGIN_ROOT)
- SHIPWRIGHT_PROJECT_ROOT: resolved via resolve_project_root() for
  subdirectory-safe monorepo support. Falls back to cwd on failure.
- SHIPWRIGHT_ROOT_SESSION_ID / SHIPWRIGHT_LOOP_ID / SHIPWRIGHT_LOOP_UNIT_ID:
  autonomous-loop env vars, only emitted when set by the parent runner.

Also writes SHIPWRIGHT_SESSION_ID into CLAUDE_ENV_FILE (if provided) so
bash subprocesses inherit it — additionalContext alone does not reach
child processes spawned by Claude's Bash tool.

**Phase-Quality injection (PR 4, Szenario C):** at SessionStart this
hook reads the transient findings summary (``phase_quality.SUMMARY_PATH``,
under the gitignored ``skill-compliance`` dir since iterate-2026-06-09) and
appends up to 5 Tier-1 FAILs as ``additionalContext``.
Only Tier-1 FAILs are injected; Tier-2 (heuristic) is silent (plan § 4.3).

**Default is ON** (``audit_inject``) since the Phase-Quality epic
completed — rollout calculus shifted from "wait 6 weeks, opt in" to
"flip now, opt out on noise." Set
``SHIPWRIGHT_PHASE_QUALITY_MODE=audit_only`` to disable injection and
fall back to silent-file-only observability.

This replaces the 8 per-plugin copies that used to live in
plugins/*/scripts/hooks/capture-session-id.py. All plugin hooks.json
files now reference this single canonical implementation.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

# Make shared lib importable regardless of which plugin invokes this hook.
# This file lives at shared/scripts/hooks/, so parents[1] is shared/scripts/
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# Sibling module in this same hooks/ dir — flat import, matching
# check_required_checks_hook.py's required_checks_state convention.
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from session_start_phase_quality import (  # noqa: E402
    build_phase_quality_injection,
    phase_quality_inject_enabled,
)


def _resolve_root() -> str:
    """Find the Shipwright project root, tolerating subdirectory layouts."""
    try:
        from lib.project_root import resolve_project_root
        return str(resolve_project_root())
    except (ImportError, ValueError):
        return os.getcwd()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0  # Hooks should never fail

    session_id = payload.get("session_id")
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")

    if not session_id:
        return 0

    context_parts: list[str] = []

    if os.environ.get("SHIPWRIGHT_SESSION_ID") != session_id:
        context_parts.append(f"SHIPWRIGHT_SESSION_ID={session_id}")

    if plugin_root:
        context_parts.append(f"SHIPWRIGHT_PLUGIN_ROOT={plugin_root}")

    project_root = _resolve_root()
    context_parts.append(f"SHIPWRIGHT_PROJECT_ROOT={project_root}")

    # Autonomous-loop propagation (only emitted when parent runner set them).
    for var in (
        "SHIPWRIGHT_ROOT_SESSION_ID",
        "SHIPWRIGHT_LOOP_ID",
        "SHIPWRIGHT_LOOP_UNIT_ID",
    ):
        value = os.environ.get(var)
        if value:
            context_parts.append(f"{var}={value}")

    # Phase-Quality Tier-1 FAIL injection. The hook is registered in every
    # plugin, so one SessionStart event fires it ~12x with the identical
    # block. Dedup to once-per-event via claim_once (event-scoped on the
    # session id, TTL-armed so a later resume/compact re-emits). Fail-open:
    # claim_once returns True on any guard error, so a real FAIL is never
    # dropped. Only the block is gated — env context is emitted every time.
    # audit_only short-circuits before claiming so the opt-out leaves no
    # cache file. Non-blocking; injection errors never propagate.
    if phase_quality_inject_enabled():
        try:
            from lib.event_once import claim_once
            claim_path = (
                Path(project_root) / ".shipwright" / ".cache"
                / f"sessionstart-{session_id}.claim"
            )
            may_emit = claim_once(claim_path)
        except Exception:  # noqa: BLE001
            may_emit = True
        if may_emit:
            try:
                injection = build_phase_quality_injection(project_root)
            except Exception:  # noqa: BLE001
                injection = ""
            if injection:
                context_parts.append(injection)

    if context_parts:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_parts),
            }
        }))

    # CLAUDE_ENV_FILE fallback so these vars reach bash subprocesses —
    # additionalContext alone does not (it is text shown to the model, not an
    # OS environment). SHIPWRIGHT_LOOP_UNIT_ID joined SESSION_ID here
    # (trg-33d30377 / iterate-2026-09-11-ci-supplychain-ack-authorship): a
    # campaign runner script — record_ci_supplychain_ack.py's authorship
    # guard — reads it via plain `os.environ.get`, i.e. exactly the channel
    # this fallback exists to fill; the additionalContext-only propagation a
    # few lines up reaches the MODEL's awareness, never a Bash-tool
    # subprocess's real environment, so a guard relying on that alone would
    # be silently inert for the one scenario it exists to catch.
    #
    # SYNCED, not merely appended (doubt review, trg-33d30377): unlike
    # SESSION_ID, LOOP_UNIT_ID changes value — or disappears — across a
    # session's lifetime (set for a runner's unit, absent once it returns).
    # An earlier append-only version left a stale `export
    # SHIPWRIGHT_LOOP_UNIT_ID=<old unit>` line in place forever once any
    # unit had run, which could make the guard's own documented recovery
    # path ("act from the orchestrator's own shell once the unit has
    # returned") unreachable if CLAUDE_ENV_FILE is shared across that
    # session's Bash-tool calls. Each SessionStart now rewrites this file's
    # line for each tracked var to match this hook's own CURRENT ambient
    # environment exactly — present with a new value replaces the old line;
    # absent removes any existing line for it.
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        # None = "must not be exported here" (removes any stale line instead
        # of leaving it). shlex.quote: both values are environment-sourced
        # (harness-controlled in the intended flow), but nothing upstream
        # enforces a safe charset before this write — campaign-mode.md Step
        # 3b has the orchestrator interpolate a JSON `id` field straight
        # into a literal `export` line. An unquoted value containing shell
        # metacharacters would execute arbitrary content the next time this
        # file is sourced.
        desired: dict[str, str | None] = {
            "SHIPWRIGHT_SESSION_ID": session_id,
            "SHIPWRIGHT_LOOP_UNIT_ID": os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID") or None,
        }
        try:
            try:
                with open(env_file, encoding="utf-8") as f:
                    existing_lines = f.readlines()
            except FileNotFoundError:
                existing_lines = []
            prefixes = tuple(f"export {name}=" for name in desired)
            kept = [ln for ln in existing_lines if not ln.startswith(prefixes)]
            new_lines = [
                f"export {name}={shlex.quote(value)}\n"
                for name, value in desired.items() if value is not None
            ]
            if kept != existing_lines or new_lines:
                with open(env_file, "w", encoding="utf-8") as f:
                    f.writelines(kept + new_lines)
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
