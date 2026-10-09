#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code hook: a campaign sub-iterate-runner may spawn only its five reviewers.

``sub-iterate-runner`` carries the ``Agent`` tool so it can run its own internal
reviews (``references/campaign-step-3-7-internal-reviews.md``). The brief limits
it to five ``subagent_type``s and two re-reviews per stage -- prose a model can
skip, and the Agent tool would otherwise let it recurse or fan out. This
``PreToolUse`` hook turns both limits into a deny.

The subagent is recognised from the hook payload, not from the environment: a
hook inherits the Claude Code process env, so a ``SHIPWRIGHT_LOOP_UNIT_ID``
exported in the runner's Bash never reaches it. Claude Code adds ``agent_id`` /
``agent_type`` to every hook fired inside a subagent; the main session has
neither, so it is never touched.

State for the cap is one JSON file per ``agent_id`` under
``.shipwright/runtime/runner-spawns/`` (gitignored by the ``/.shipwright/*``
canon rule). Fail-open throughout, as with the worktree gate: any error means
allow. ``SHIPWRIGHT_RUNNER_SPAWN_GUARD=off`` lifts it. Threat model: a forgetful
cooperative model, not an adversary."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_OFF_ENV = "SHIPWRIGHT_RUNNER_SPAWN_GUARD"
_RUNNER = "sub-iterate-runner"
_SPAWN_TOOLS = frozenset({"Agent", "Task"})  # Task = the pre-v2.1.63 name
ALLOWED = frozenset({
    "architecture-internal-reviewer", "opus-plan-reviewer",
    "spec-reviewer", "code-reviewer", "doubt-reviewer",
})
#: The first review plus the 2 re-review rounds the brief allows per stage.
MAX_SPAWNS_PER_TYPE = 3
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")


def _bare(name: object) -> str:
    """``shipwright-build:spec-reviewer`` -> ``spec-reviewer``."""
    return name.rsplit(":", 1)[-1].strip() if isinstance(name, str) else ""


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason + (
            " (campaign-step-3-7-internal-reviews.md). Record the pass "
            "`not_run --reason-code delegated-to-orchestrator` and let 3f-bis cover it; "
            f"only the user can lift this guard ({_OFF_ENV}=off)."),
    }}


def _state_file(cwd: Path, agent_id: str) -> Path:
    from lib.repo_root import main_repo_root_or

    return main_repo_root_or(cwd) / ".shipwright" / "runtime" / "runner-spawns" / f"{agent_id}.json"


def _count_spawn(cwd: Path, agent_id: str, kind: str) -> int:
    """Record one spawn of ``kind`` and return how many there now are."""
    path = _state_file(cwd, agent_id)
    try:
        counts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        counts = {}
    if not isinstance(counts, dict):
        counts = {}
    counts[kind] = int(counts.get(kind, 0)) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(counts), encoding="utf-8")
    return counts[kind]


def handle_payload(payload: dict) -> dict | None:
    """Decision for one hook payload; ``None`` = take no position (allow)."""
    if os.environ.get(_OFF_ENV, "").strip().lower() in {"off", "0", "false"}:
        return None
    if payload.get("hook_event_name") != "PreToolUse" or payload.get("tool_name") not in _SPAWN_TOOLS:
        return None
    agent_id = payload.get("agent_id")
    if not (isinstance(agent_id, str) and _SAFE_ID.fullmatch(agent_id)):
        return None  # main session, or an id we will not turn into a file name
    if _bare(payload.get("agent_type")) != _RUNNER:
        return None  # some other subagent: not this guard's business
    tool_input = payload.get("tool_input")
    kind = _bare(tool_input.get("subagent_type")) if isinstance(tool_input, dict) else ""
    if kind not in ALLOWED:
        return _deny(
            f"A campaign sub-iterate-runner may spawn only {', '.join(sorted(ALLOWED))}; "
            f"got {kind or 'no subagent_type (the default general-purpose agent)'}")
    cwd_raw = payload.get("cwd")
    if not (isinstance(cwd_raw, str) and cwd_raw.strip()):
        return None
    n = _count_spawn(Path(cwd_raw), agent_id, kind)
    if n > MAX_SPAWNS_PER_TYPE:
        return _deny(f"{kind} was already spawned {MAX_SPAWNS_PER_TYPE} times by this runner "
                     "(first review + 2 re-review rounds)")
    return None


def _find_shared_scripts() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"


def main() -> int:
    try:
        sys.path.insert(0, str(_find_shared_scripts()))
        payload = json.load(sys.stdin)
        decision = handle_payload(payload) if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 -- a hook must never crash the turn
        return 0
    if decision is not None:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
