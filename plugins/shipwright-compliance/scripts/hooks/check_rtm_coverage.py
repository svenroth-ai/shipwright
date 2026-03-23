#!/usr/bin/env python3
"""PreToolUse hook: Soft-block git commit when RTM coverage is below threshold.

Reads the compliance traceability matrix from compliance/traceability-matrix.md,
extracts coverage percentage, and blocks commit if below threshold.

Exit codes:
  0 = allow (no compliance data yet, or coverage sufficient)
  2 = soft-block (user can say "Continue anyway", gets logged)

The user can override by saying "Continue anyway". If they do, Claude should
log the override to agent_docs/compliance_overrides.log.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any


def _hook_block(reason: str, details: dict[str, Any]) -> dict[str, Any]:
    """Build soft-block hook output with override support."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"BLOCKED: {reason}\n\n"
                "The user may say 'Continue anyway' to override this check. "
                "If they do, log the override to agent_docs/compliance_overrides.log "
                "with timestamp, hook name 'check_rtm_coverage', and reason.\n\n"
                "Note: Coverage gap will be flagged again at next compliance checkpoint."
            ),
            "blocked": True,
            "reason": reason,
            "details": details,
        }
    }


def get_coverage_from_rtm(project_root: str) -> int | None:
    """Parse coverage percentage from traceability-matrix.md.

    Returns coverage as int (0-100) or None if file doesn't exist.
    """
    rtm_path = os.path.join(project_root, "compliance", "traceability-matrix.md")
    if not os.path.exists(rtm_path):
        return None

    try:
        with open(rtm_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    # Match "| Traceability coverage | NN% |"
    match = re.search(r"Traceability coverage\s*\|\s*(\d+)%", content)
    if match:
        return int(match.group(1))
    return None


def get_threshold(project_root: str) -> float:
    """Load RTM coverage threshold from compliance config."""
    config_path = os.path.join(project_root, "shipwright_compliance_config.json")
    if not os.path.exists(config_path):
        return 0.80  # default

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("enforcement", {}).get("rtm_coverage_min", 0.80)
    except (json.JSONDecodeError, OSError):
        return 0.80


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0  # Can't parse payload, allow

    # Only check Bash tool calls containing git commit
    command = payload.get("tool_input", {}).get("command", "")
    if "git commit" not in command and "git -c" not in command:
        return 0

    # Determine project root from cwd
    project_root = os.getcwd()

    # If no compliance data yet (early pipeline), allow
    coverage = get_coverage_from_rtm(project_root)
    if coverage is None:
        return 0

    threshold = get_threshold(project_root)
    threshold_pct = int(threshold * 100)

    if coverage < threshold_pct:
        # Find uncovered sections for actionable feedback
        uncovered = _find_uncovered_sections(project_root)
        print(json.dumps(_hook_block(
            reason=f"RTM coverage {coverage}% < {threshold_pct}% threshold",
            details={
                "coverage_pct": coverage,
                "threshold_pct": threshold_pct,
                "uncovered_sections": uncovered,
            },
        )))
        return 2

    return 0


def _find_uncovered_sections(project_root: str) -> list[str]:
    """Find sections without commits from the RTM."""
    rtm_path = os.path.join(project_root, "compliance", "traceability-matrix.md")
    uncovered = []
    try:
        with open(rtm_path, encoding="utf-8") as f:
            for line in f:
                # Table rows: "| split | section | — | ..." means no commit
                if line.startswith("|") and "| — |" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3 and parts[2]:  # section name
                        uncovered.append(parts[2])
    except OSError:
        pass
    return uncovered


if __name__ == "__main__":
    sys.exit(main())
