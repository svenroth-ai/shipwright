#!/usr/bin/env python3
"""Stop hook: Check documentation completeness before session ends.

Verifies that decision_log.md and session_handoff.md are up to date.
Outputs a warning if documentation is missing but does NOT block.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0

    # Try to find project root from cwd or env
    project_root = Path.cwd()

    warnings = []

    agent_docs = project_root / ".shipwright" / "agent_docs"
    if agent_docs.is_dir():
        decision_log = agent_docs / "decision_log.md"
        if not decision_log.exists():
            warnings.append(".shipwright/agent_docs/decision_log.md not found")

        handoff = agent_docs / "session_handoff.md"
        if not handoff.exists():
            warnings.append(".shipwright/agent_docs/session_handoff.md not found — consider generating before ending session")

    if warnings:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": "Documentation check: " + "; ".join(warnings),
            }
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
