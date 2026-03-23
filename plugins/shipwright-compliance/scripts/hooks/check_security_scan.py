#!/usr/bin/env python3
"""PreToolUse hook: Soft-block deploy when critical security findings exist.

Checks compliance reports for unresolved critical findings and blocks
deploy commands if any remain.

Exit codes:
  0 = allow (no findings data, or no critical findings)
  2 = soft-block (user can say "Continue anyway", gets logged)
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
                "with timestamp, hook name 'check_security_scan', and reason.\n\n"
                "Note: Security findings will be flagged again before production deploy."
            ),
            "blocked": True,
            "reason": reason,
            "details": details,
        }
    }


def get_unresolved_findings(project_root: str) -> tuple[int, list[str]]:
    """Parse unresolved findings count and details from RTM.

    Returns (unresolved_count, finding_descriptions).
    """
    rtm_path = os.path.join(project_root, "compliance", "traceability-matrix.md")
    if not os.path.exists(rtm_path):
        return 0, []

    try:
        with open(rtm_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return 0, []

    # Match "| Unresolved findings | N |"
    match = re.search(r"Unresolved findings\s*\|\s*(\d+)", content)
    unresolved = int(match.group(1)) if match else 0

    # Collect sections with FAIL status
    failing = []
    for line in content.splitlines():
        if line.startswith("|") and "FAIL" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                failing.append(parts[2])  # section name

    return unresolved, failing


def get_threshold(project_root: str) -> int:
    """Load allowed critical findings from compliance config."""
    config_path = os.path.join(project_root, "shipwright_compliance_config.json")
    if not os.path.exists(config_path):
        return 0  # default: zero tolerance

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("enforcement", {}).get("allowed_critical_findings", 0)
    except (json.JSONDecodeError, OSError):
        return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0

    # Only check Bash tool calls with deploy-like commands
    command = payload.get("tool_input", {}).get("command", "")
    deploy_patterns = ["deploy", "jelastic", "vercel", "fly deploy", "railway up"]
    if not any(p in command.lower() for p in deploy_patterns):
        return 0

    project_root = os.getcwd()

    unresolved, failing_sections = get_unresolved_findings(project_root)
    if unresolved == 0:
        return 0

    threshold = get_threshold(project_root)
    if unresolved <= threshold:
        return 0

    print(json.dumps(_hook_block(
        reason=f"{unresolved} unresolved finding(s) exceed allowed threshold ({threshold})",
        details={
            "unresolved_findings": unresolved,
            "allowed_threshold": threshold,
            "failing_sections": failing_sections,
        },
    )))
    return 2


if __name__ == "__main__":
    sys.exit(main())
