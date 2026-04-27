#!/usr/bin/env python3
"""Phase-skill Step 0 Context Recovery tool.

Called by every phase Skill (project, design, plan, build, test, security,
changelog, deploy) as their FIRST action when running inside an active
shipwright-run pipeline. Spike F0 finding: phase-discovery env vars set
by SessionStart hook do NOT propagate to Bash-tool subprocesses, so the
Skill must:
  1. Read phaseTaskId from the SHIPWRIGHT-PIPELINE-CONTEXT block injected
     by phase_session_start.py via additionalContext.
  2. Call this tool with --phase-task-id <id>.
  3. Read the prior-phase artifacts this tool surfaces.

Standalone branch: if no --phase-task-id is provided OR the lookup fails
(no run_config.json, schema v1, no matching task), the tool prints a
"standalone" mode JSON and exits 0. The Skill is expected to ignore
pipeline metadata and proceed with its normal Step 1.

Usage:
    uv run get_phase_context.py --phase-task-id <ptk-XXXX> [--project-root <path>]

Output: structured JSON on stdout with the following shape:
    {
      "mode": "pipeline" | "standalone",
      "runId": "...",                          # only when mode=pipeline
      "phaseTaskId": "ptk-XXXX",               # echoed back
      "phase": "build",
      "splitId": "01-core" | null,
      "version": 2,
      "prerequisites": [
        {"phaseTaskId": "ptk-PRED", "phase": "plan", "splitId": null,
         "status": "done", "artifacts": [...]}
      ],
      "runConditions": {...},
      "splits_frozen": [...],
      "skill_artifacts_to_read": [
        ".shipwright/agent_docs/sections/01-core/...",
        "shipwright_plan_config.json",
        ...
      ],
      "next_action_hint": "Read the artifacts in skill_artifacts_to_read, then proceed with skill Step 1."
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


# Add lib/ for imports — both shared/scripts/lib (if present) and the run plugin
_THIS_DIR = Path(__file__).resolve().parent
_SHARED_LIB = _THIS_DIR.parent / "lib"
if _SHARED_LIB.exists():
    sys.path.insert(0, str(_SHARED_LIB))

# The phase_task_lifecycle lib lives in the run plugin.
_RUN_LIB = (
    _THIS_DIR.parent.parent.parent / "plugins" / "shipwright-run" / "scripts" / "lib"
)
sys.path.insert(0, str(_RUN_LIB))


CONFIG_NAME = "shipwright_run_config.json"


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
    "security": ["compliance/security-scan-report.md"],
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


def _standalone_payload(reason: str, phase_task_id: Optional[str]) -> dict[str, Any]:
    return {
        "mode": "standalone",
        "reason": reason,
        "phaseTaskId": phase_task_id,
        "next_action_hint": (
            "No active shipwright-run pipeline detected. Proceed with the "
            "skill's normal Step 1 — there is no pipeline metadata to load."
        ),
    }


def build_phase_context(
    project_root: Path, phase_task_id: Optional[str],
) -> dict[str, Any]:
    """Return the structured Step-0 payload. Never raises."""
    if not phase_task_id:
        return _standalone_payload("no_phase_task_id", None)

    config_path = project_root / CONFIG_NAME
    if not config_path.exists():
        return _standalone_payload("no_run_config", phase_task_id)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _standalone_payload("run_config_parse_error", phase_task_id)

    if config.get("schemaVersion") != 2:
        return _standalone_payload("schema_v1_legacy", phase_task_id)

    tasks = config.get("phase_tasks") or []
    task = next((t for t in tasks if t.get("phaseTaskId") == phase_task_id), None)
    if task is None:
        return _standalone_payload("phase_task_id_not_found", phase_task_id)

    # Resolve prerequisites
    by_id = {t.get("phaseTaskId"): t for t in tasks}
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

    return {
        "mode": "pipeline",
        "runId": config.get("runId"),
        "phaseTaskId": task.get("phaseTaskId"),
        "phase": task.get("phase"),
        "splitId": task.get("splitId"),
        "version": task.get("version"),
        "slashCommand": task.get("slashCommand"),
        "prerequisites": prereqs_out,
        "runConditions": config.get("runConditions") or {},
        "splits_frozen": config.get("splits_frozen") or [],
        "skill_artifacts_to_read": _suggest_artifacts(
            task.get("phase") or "", task.get("splitId"),
        ),
        "next_action_hint": (
            "Read the files/dirs listed in skill_artifacts_to_read, then "
            "proceed with the skill's normal Step 1. The pipeline will track "
            "your phase status via the SessionStop hook — you do not need to "
            "manage it manually."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase Session Context Recovery")
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--phase-task-id", default=None,
        help="phaseTaskId from the SHIPWRIGHT-PIPELINE-CONTEXT block. "
             "If omitted, prints standalone-mode payload.",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    payload = build_phase_context(project_root, args.phase_task_id)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
