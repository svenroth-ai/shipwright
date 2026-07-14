#!/usr/bin/env python3
"""Phase Step-0 Context Recovery tool + the phase skills' invocation-mode resolver.

Two callers, one verdict:

* **The phase-runner's Step 0** (``plugins/shipwright-run/agents/phase-runner.md``) runs
  this to surface the prior-phase artifacts its phase depends on.
* **Every driven phase skill's "Detect Invocation Mode" step** runs this to decide whether
  it is a pipeline phase or a hand-invoked standalone run.

They MUST agree, so they ask the same tool. Before
``iterate-2026-07-14-phase-invocation-mode`` the skills answered it themselves, in prose,
from the **v1** fields ``status`` + ``current_step`` — which the **v2** pipeline never
advances (``phase_task_lifecycle`` writes ``phase_tasks[]``; ``config_factory`` stamps
``current_step`` once at run creation and nothing moves it). Every driven phase past the
first therefore self-classified as *standalone*. The mode logic now lives in
``shared/scripts/lib/phase_invocation_mode.py`` — see that module for the full rationale,
the three-outcome contract, and the token trust model.

**How the phaseTaskId reaches the caller.** It used to arrive in a
``SHIPWRIGHT-PIPELINE-CONTEXT`` block that the ``phase_session_start`` SessionStart hook
injected into an external phase session. That hook is DELETED with the multi-session
engine, and it could never have fired in the surviving mode anyway (the phase runner is a
SUBAGENT of the master, so it has no bound Claude session whose id could match a
``phase_tasks[].sessionUuid``). The master now passes it directly: ``single-session-next``
returns the ``phaseTaskId`` in its dispatch descriptor, and the master briefs the
phase-runner subagent to run this tool as its first action.

Usage:
    uv run get_phase_context.py --phase-task-id <ptk-XXXX> [--phase build] \
        [--project-root <path>]

Omit ``--phase-task-id`` when you were NOT dispatched by the orchestrator: that is the
only input that yields ``standalone``. Pass ``--phase`` (your own phase) so a stale or
wrong-phase token is rejected rather than honoured.

Exit codes: ``0`` for ``pipeline`` / ``standalone``; ``2`` for ``error`` — a token was
supplied but does not resolve. On ``2`` the caller STOPs; it must NOT continue as
standalone.

Output: structured JSON on stdout.

    mode=pipeline:
      {"mode": "pipeline", "runId", "phaseTaskId", "phase", "splitId", "version",
       "slashCommand", "prerequisites": [{"phaseTaskId", "phase", "splitId", "status",
       "artifacts"}], "runConditions", "splits_frozen", "skill_artifacts_to_read": [...],
       "next_action_hint"}

    mode=standalone:
      {"mode": "standalone", "reason": "no_phase_task_id", "phaseTaskId": null,
       "pipeline_active": bool, "active_phases": [...],
       "requires_out_of_sequence_warning": bool, "next_action_hint"}

    mode=error:
      {"mode": "error", "reason", "phaseTaskId", "message", "next_action_hint"}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

# Add shared/scripts/lib for the invocation-mode resolver.
_THIS_DIR = Path(__file__).resolve().parent
_SHARED_LIB = _THIS_DIR.parent / "lib"
if _SHARED_LIB.exists():
    sys.path.insert(0, str(_SHARED_LIB))

from phase_invocation_mode import (  # noqa: E402
    ERROR,
    PIPELINE,
    resolve_invocation_mode,
)

EXIT_OK = 0
EXIT_UNRESOLVED_TOKEN = 2


# ---------------------------------------------------------------------------
# Per-phase artifact suggestions
# ---------------------------------------------------------------------------

# Maps each phase to (a) its own primary config file and (b) artifact paths
# its predecessors typically produce. Intentionally minimal — F5 will tune
# per-skill based on what each Skill actually needs to read.
PHASE_OWN_ARTIFACTS: dict[str, list[str]] = {
    "project": [".shipwright/planning/requirements.md"],
    "design": [".shipwright/designs/", "shipwright_design_config.json"],
    "plan": [".shipwright/agent_docs/sections/", "shipwright_plan_config.json"],
    "build": ["shipwright_build_config.json"],
    "test": ["shipwright_test_results.json"],
    "security": [".shipwright/compliance/security-scan-report.md"],
    "changelog": ["CHANGELOG.md"],
    "deploy": ["shipwright_deploy_config.json"],
}

# What predecessor artifacts this phase typically reads.
PHASE_PREREQ_ARTIFACTS: dict[str, list[str]] = {
    "design": [".shipwright/planning/requirements.md", "shipwright_project_config.json"],
    "plan": [".shipwright/planning/requirements.md", "shipwright_design_config.json",
             ".shipwright/designs/"],
    "build": [".shipwright/agent_docs/sections/", "shipwright_plan_config.json"],
    "test": ["shipwright_build_config.json"],
    "security": ["shipwright_test_results.json"],
    "changelog": ["shipwright_test_results.json"],
    "deploy": ["CHANGELOG.md"],
}


def _suggest_artifacts(phase: str, split_id: Optional[str]) -> list[str]:
    """Return a deduplicated list of artifact paths the Skill should read.

    Combines the phase's prerequisite artifacts with split-scoped subdirs
    when applicable (e.g. build/01-core reads .shipwright/agent_docs/sections/01-core/).
    """
    paths: list[str] = list(PHASE_PREREQ_ARTIFACTS.get(phase, []))
    if split_id:
        # Replace any generic .shipwright/agent_docs/sections/ entry with the split-scoped one
        scoped = f".shipwright/agent_docs/sections/{split_id}/"
        paths = [p if p != ".shipwright/agent_docs/sections/" else scoped for p in paths]
        if scoped not in paths and ".shipwright/agent_docs/sections/" not in paths:
            paths.append(scoped)
    # Dedupe preserving order
    seen = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Core lookup
# ---------------------------------------------------------------------------


def build_phase_context(
    project_root: Path,
    phase_task_id: Optional[str],
    phase: Optional[str] = None,
) -> dict[str, Any]:
    """Return the structured Step-0 payload. Never raises.

    Delegates the verdict to :func:`phase_invocation_mode.resolve_invocation_mode` — the
    single authority both this tool and the phase skills consult — and enriches a
    ``pipeline`` verdict with the prior-phase artifacts the runner should read.
    ``standalone`` and ``error`` payloads pass through verbatim.
    """
    payload, task, config = resolve_invocation_mode(project_root, phase_task_id, phase)
    if payload["mode"] != PIPELINE:
        return payload

    assert task is not None and config is not None  # guaranteed by the PIPELINE verdict

    by_id = {t.get("phaseTaskId"): t for t in (config.get("phase_tasks") or [])}
    prereqs_out: list[dict[str, Any]] = []
    for pid in task.get("prerequisites") or []:
        pred = by_id.get(pid)
        if pred is None:
            prereqs_out.append({"phaseTaskId": pid, "status": "missing"})
            continue
        prereqs_out.append({
            "phaseTaskId": pid,
            "phase": pred.get("phase"),
            "splitId": pred.get("splitId"),
            "status": pred.get("status"),
            "artifacts": PHASE_OWN_ARTIFACTS.get(pred.get("phase") or "", []),
        })

    payload["prerequisites"] = prereqs_out
    payload["skill_artifacts_to_read"] = _suggest_artifacts(
        task.get("phase") or "", task.get("splitId"),
    )
    payload["next_action_hint"] = (
        "Read the files/dirs listed in skill_artifacts_to_read, then proceed with the "
        "skill's normal Step 1. You do not need to manage your phase status: the "
        "orchestrator records it when it applies your result (single-session-apply)."
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase Session Context Recovery")
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--phase-task-id", default=None,
        help="phaseTaskId, as handed to you by the orchestrator in its dispatch. "
             "Omit it ONLY if you were not dispatched — that is the sole input that "
             "yields standalone mode.",
    )
    parser.add_argument(
        "--phase", default=None,
        help="Your own phase (project|design|plan|build|test|changelog|deploy). When "
             "given, a token belonging to a different phase is rejected instead of "
             "honoured.",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    payload = build_phase_context(project_root, args.phase_task_id, args.phase)
    print(json.dumps(payload, indent=2))
    return EXIT_UNRESOLVED_TOKEN if payload["mode"] == ERROR else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
